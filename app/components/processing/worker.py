import logging
import shutil
import tempfile
from datetime import timedelta
from pathlib import Path

from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert

from app.components.processing.models import (
    Note,
    NotePart,
    ProviderGate,
    Transcript,
    TranscriptChunk,
    now,
)
from app.components.processing.notes import digest, note_text, split_content
from app.components.processing.prepare import PreparationError, prepare_audio
from app.components.processing.providers import ProviderFailure
from app.components.processing.queue import LeaseLost, claim, heartbeat, mutate, release
from app.components.processing.schemas import LectureNote, Transcription
from app.components.recordings.storage import LocalRecordingStorage

logger = logging.getLogger("archy")


class Deferred(Exception):
    def __init__(self, seconds):
        self.seconds = seconds


def gate_key(provider, model):
    return ("fixture:" if provider.name == "fixture" else "") + model


def reserve(sessions, held, provider, model, interval):
    def operation(session, job):
        key = gate_key(provider, model)
        session.execute(
            insert(ProviderGate).values(model=key, available_at=now()).on_conflict_do_nothing()
        )
        gate = session.scalar(
            select(ProviderGate).where(ProviderGate.model == key).with_for_update()
        )
        if provider.name != "fixture" and gate.available_at > now():
            raise Deferred(max(1, int((gate.available_at - now()).total_seconds()) + 1))
        gate.available_at = now() + timedelta(seconds=interval if provider.name != "fixture" else 0)
        job.provider = provider.name

    mutate(sessions, held, operation)


def gate_delay(session, provider, model, seconds):
    key = gate_key(provider, model)
    gate = session.scalar(select(ProviderGate).where(ProviderGate.model == key).with_for_update())
    if gate is not None:
        gate.available_at = max(gate.available_at, now() + timedelta(seconds=seconds))


def save_chunk(sessions, held, sequence, data, offset, samples):
    parsed = Transcription.model_validate(data)
    length = samples / 16000
    if any(s.end > length + 1 for s in parsed.segments):
        raise ProviderFailure("invalid_provider_output")
    document = parsed.model_dump()
    document["segments"] = [
        {"start": s.start + offset, "end": s.end + offset, "text": s.text} for s in parsed.segments
    ]

    def operation(session, job):
        session.add(TranscriptChunk(job_id=job.id, sequence=sequence, document=document))
        job.transcription_attempts = 0
        job.deferrals = 0
        job.error_code = ""

    mutate(sessions, held, operation)


def transcribe(sessions, settings, held, provider):
    config = held.config
    root = settings.storage_root / "processing"
    root.mkdir(parents=True, exist_ok=True, mode=0o700)
    root.chmod(0o700)
    directory = Path(tempfile.mkdtemp(prefix=f"{held.id}-{held.token}-", dir=root))
    try:
        source = LocalRecordingStorage(settings.storage_root).recording_path(held.recording_id)
        manifest = prepare_audio(source, directory, config)

        def existing(session, job):
            if job.manifest is None:
                job.manifest = manifest
            elif job.manifest != manifest:
                raise ProviderFailure("audio_changed", permanent=True)
            saved = {
                row.sequence: row.document
                for row in session.scalars(
                    select(TranscriptChunk).where(TranscriptChunk.job_id == job.id)
                ).all()
            }
            return saved, job.transcription_model

        saved, model = mutate(sessions, held, existing)
        for sequence, part in enumerate(manifest["segments"]):
            if sequence not in saved:
                reserve(sessions, held, provider, model, 10)
                data = provider.transcribe(directory / part["file"], config)
                save_chunk(
                    sessions, held, sequence, data, part["startSample"] / 16000, part["samples"]
                )
                mutate(
                    sessions,
                    held,
                    lambda session, job: gate_delay(session, provider, model, provider.next_delay),
                )
                return

        def assemble(session, job):
            ordered = [saved[i] for i in range(len(manifest["segments"]))]
            weights = {
                lang: sum(
                    manifest["segments"][i]["samples"]
                    for i, row in enumerate(ordered)
                    if row["language"] == lang
                )
                for lang in ("ko", "en")
            }
            language = max(weights, key=weights.get)
            try:
                parsed = Transcription.model_validate(
                    {
                        "text": "\n".join(d["text"] for d in ordered),
                        "segments": [s for d in ordered for s in d["segments"]],
                        "language": language,
                    }
                )
            except ValidationError:
                raise ProviderFailure("invalid_provider_output", permanent=True) from None
            session.add(
                Transcript(
                    job_id=job.id,
                    text=parsed.text,
                    segments=[s.model_dump() for s in parsed.segments],
                    language=language,
                    provider=provider.name,
                    model=model,
                )
            )
            job.stage = "TRANSCRIBED"

        mutate(sessions, held, assemble)
    finally:
        shutil.rmtree(directory, ignore_errors=True)


def summarize(sessions, held, provider):
    def load(session, job):
        transcript = session.scalar(select(Transcript).where(Transcript.job_id == job.id))
        parts = {
            (p.level, p.sequence): (p.source_digest, p.document)
            for p in session.scalars(select(NotePart).where(NotePart.job_id == job.id))
        }
        job.stage = "SUMMARIZING"
        return transcript.text, transcript.language, parts, job.summary_model

    source, language, saved, model = mutate(sessions, held, load)
    for level in range(8):
        pieces = split_content(source, language, held.config)
        documents = []
        for sequence, piece in enumerate(pieces):
            previous = saved.get((level, sequence))
            if previous:
                if previous[0] != digest(piece):
                    raise ProviderFailure("summary_changed", permanent=True)
                documents.append(previous[1])
            else:
                reserve(sessions, held, provider, model, held.config.summary_interval)
                document = LectureNote.model_validate(
                    provider.summarize(piece, language, held.config)
                ).model_dump()

                def save(
                    session, job, level=level, sequence=sequence, piece=piece, document=document
                ):
                    session.add(
                        NotePart(
                            job_id=job.id,
                            level=level,
                            sequence=sequence,
                            source_digest=digest(piece),
                            document=document,
                        )
                    )
                    job.summary_attempts = 0
                    job.deferrals = 0
                    job.error_code = ""
                    gate_delay(session, provider, model, provider.next_delay)

                mutate(sessions, held, save)
                return
        if len(documents) == 1:

            def complete(session, job, document=documents[0]):
                session.add(
                    Note(
                        job_id=job.id,
                        document=document,
                        language=language,
                        provider=provider.name,
                        model=model,
                        prompt_version=job.prompt_version,
                    )
                )
                job.stage = "COMPLETED"
                job.error_code = ""

            mutate(sessions, held, complete)
            return
        reduced = "\n".join(note_text(d) for d in documents)
        if len(reduced.encode()) >= len(source.encode()):
            raise ProviderFailure("summary_budget", permanent=True)
        source = reduced
    raise ProviderFailure("summary_budget", permanent=True)


def fail(sessions, held, provider, error):
    def operation(session, job):
        if job.stage in ("COMPLETED", "FAILED"):
            release(job)
            return
        summarizing = job.stage in ("TRANSCRIBED", "SUMMARIZING")
        model = job.summary_model if summarizing else job.transcription_model
        if error.quota:
            job.deferrals += 1
            delay = min(86400, max(60, error.retry_after or 3600))
            job.error_code = "quota_wait"
            gate_delay(session, provider, model, delay)
            terminal = job.deferrals >= held.config.max_deferrals
        else:
            field = "summary_attempts" if summarizing else "transcription_attempts"
            attempts = getattr(job, field) + 1
            setattr(job, field, attempts)
            terminal = error.permanent or attempts >= held.config.max_attempts
            delay = min(900, 30 * 2 ** (attempts - 1))
            job.error_code = error.code
        if terminal:
            job.stage = "FAILED"
        release(job, 0 if terminal else delay)

    mutate(sessions, held, operation)


def run_once(sessions, settings, provider):
    held = claim(sessions)
    if held is None:
        return False
    try:
        with heartbeat(sessions, held):
            stage = mutate(sessions, held, lambda session, job: job.stage)
            if stage == "TRANSCRIBING":
                transcribe(sessions, settings, held, provider)
            else:
                summarize(sessions, held, provider)
        mutate(sessions, held, lambda session, job: release(job))
    except Deferred as error:
        mutate(sessions, held, lambda session, job, delay=error.seconds: release(job, delay))
    except LeaseLost:
        logger.warning({"event": "processing_lease_lost", "job_id": str(held.id)})
    except ProviderFailure as error:
        try:
            fail(sessions, held, provider, error)
        except LeaseLost:
            pass
    except PreparationError:
        try:
            fail(sessions, held, provider, ProviderFailure("audio_preparation", permanent=True))
        except LeaseLost:
            pass
    except Exception:
        try:
            fail(sessions, held, provider, ProviderFailure("processing_unavailable"))
        except LeaseLost:
            pass
        logger.warning({"event": "processing_failed", "job_id": str(held.id)})
    return True
