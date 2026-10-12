from dataclasses import replace
from datetime import timedelta

from sqlalchemy import delete, select

from app.components.processing.models import (
    Job,
    Note,
    NotePart,
    ProviderGate,
    Transcript,
    TranscriptChunk,
    now,
)
from app.components.processing.providers import FixtureProvider, ProviderFailure
from app.components.processing.queue import claim, mutate
from app.components.processing.worker import run_once
from tests.test_processing_worker import work as work


def test_multilevel_summary_recovery_keeps_all_source_and_reuses_parts(work):
    sessions, settings, key = work
    source = "함수의 입력과 출력에 관한 강의입니다.\n" * 400
    with sessions.begin() as session:
        session.add(
            Transcript(
                job_id=key,
                text=source,
                segments=[{"start": 0.0, "end": 1.0, "text": source}],
                language="ko",
                provider="fixture",
                model="whisper-large-v3-turbo",
            )
        )
        session.get(Job, key).stage = "TRANSCRIBED"
    consumed = []

    class Capture(FixtureProvider):
        def summarize(self, source, language, config):
            consumed.append((source, language))
            return {
                "overview": "한국어 강의 요약입니다.",
                "key_concepts": ["함수의 입력과 출력"],
                "examples": [],
                "review_questions": [],
                "unclear_passages": [],
            }

    for _ in range(50):
        run_once(sessions, settings, Capture())
        with sessions() as session:
            if session.get(Job, key).stage == "COMPLETED":
                break
    with sessions() as session:
        assert session.get(Job, key).stage == "COMPLETED"
        parts = session.scalars(
            select(NotePart)
            .where(NotePart.job_id == key)
            .order_by(NotePart.level, NotePart.sequence)
        ).all()
        assert len(parts) > 2 and max(p.level for p in parts) >= 1
        first_level = len([p for p in parts if p.level == 0])
        assert "".join(s for s, language in consumed[:first_level]) == source
        assert all(language == "ko" for s, language in consumed)
        assert session.scalar(select(Note).where(Note.job_id == key)).language == "ko"
        assert len(consumed) == len(parts)


def test_completed_chunk_survives_failure_on_next_chunk(work):
    sessions, settings, key = work
    settings = replace(settings, processing=replace(settings.processing, segment_seconds=1))
    # Use two independent seconds so completion requires a second provider result.
    import wave

    from app.components.recordings.models import Recording

    with sessions.begin() as session:
        record = session.get(Recording, session.get(Job, key).recording_id)
        record.duration_seconds = 2
        session.get(Job, key).configuration = settings.processing.snapshot()
        path = settings.storage_root / "recordings" / f"{record.id}.audio"
    with wave.open(str(path), "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(8000)
        wav.writeframes(bytes(32000))
    run_once(sessions, settings, FixtureProvider())

    class Fail(FixtureProvider):
        def transcribe(self, path, config):
            raise ProviderFailure("provider_unavailable")

    run_once(sessions, settings, Fail())
    with sessions() as session:
        chunks = session.scalars(select(TranscriptChunk).where(TranscriptChunk.job_id == key)).all()
        assert len(chunks) == 1 and chunks[0].sequence == 0
    with sessions.begin() as session:
        session.get(Job, key).available_at = now()
    for _ in range(12):
        run_once(sessions, settings, FixtureProvider())
    with sessions() as session:
        transcript = session.scalar(select(Transcript).where(Transcript.job_id == key))
        assert [s["start"] for s in transcript.segments] == [0.0, 1.0]
        assert session.get(Job, key).stage == "COMPLETED"


def test_provider_credential_error_is_terminal_but_audio_remains(work):
    sessions, settings, key = work

    class Credentials(FixtureProvider):
        def transcribe(self, path, config):
            raise ProviderFailure("provider_credentials", permanent=True)

    run_once(sessions, settings, Credentials())
    with sessions() as session:
        job = session.get(Job, key)
        assert job.stage == "FAILED" and job.lease_token is None
        assert (settings.storage_root / "recordings" / f"{job.recording_id}.audio").is_file()


def test_repeated_quota_deferrals_stop_without_busy_loop(work):
    sessions, settings, key = work
    with sessions.begin() as session:
        job = session.get(Job, key)
        job.configuration = {**job.configuration, "max_deferrals": 2}

    class Quota(FixtureProvider):
        def transcribe(self, path, config):
            raise ProviderFailure("quota_wait", quota=True)

    for _ in range(2):
        with sessions.begin() as session:
            session.get(Job, key).available_at = now()
            session.execute(delete(ProviderGate).where(ProviderGate.model.like("fixture:%")))
        run_once(sessions, settings, Quota())
    with sessions() as session:
        job = session.get(Job, key)
        assert job.stage == "FAILED" and job.deferrals == 2
        assert job.transcription_attempts == 0
    assert run_once(sessions, settings, Quota()) is False


def test_completed_job_cannot_be_downgraded_by_release_failure(work):
    from app.components.processing.worker import fail

    sessions, settings, key = work
    with sessions.begin() as session:
        job = session.get(Job, key)
        job.configuration = {**job.configuration, "max_attempts": 1}
    held = claim(sessions)
    mutate(sessions, held, lambda session, job: setattr(job, "stage", "COMPLETED"))
    fail(sessions, held, FixtureProvider(), ProviderFailure("processing_unavailable"))
    with sessions() as session:
        assert session.get(Job, key).stage == "COMPLETED"
        assert session.get(Job, key).lease_token is None


def test_assembled_transcript_overflow_fails_explicitly_without_truncation(work):
    import wave

    sessions, settings, key = work
    from app.components.recordings.models import Recording

    with sessions.begin() as session:
        job = session.get(Job, key)
        job.configuration = {**job.configuration, "segment_seconds": 1}
        record = session.get(Recording, job.recording_id)
        record.duration_seconds = 2
        path = settings.storage_root / "recordings" / f"{record.id}.audio"
    with wave.open(str(path), "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(8000)
        wav.writeframes(bytes(32000))
    for _ in range(2):
        run_once(sessions, settings, FixtureProvider())
    with sessions.begin() as session:
        chunks = session.scalars(select(TranscriptChunk).where(TranscriptChunk.job_id == key)).all()
        assert len(chunks) == 2
        for chunk in chunks:
            chunk.document = {**chunk.document, "text": "x" * 100001}
    run_once(sessions, settings, FixtureProvider())
    with sessions() as session:
        job = session.get(Job, key)
        assert job.stage == "FAILED" and job.error_code == "invalid_provider_output"
        assert session.scalar(select(Transcript).where(Transcript.job_id == key)) is None
        assert all(
            len(c.document["text"]) == 100001
            for c in session.scalars(select(TranscriptChunk).where(TranscriptChunk.job_id == key))
        )


def test_fresh_worker_registers_models_and_reclaims_crash_temporary_audio(work):
    import os
    import subprocess
    import sys
    import time

    sessions, settings, key = work
    held = claim(sessions)
    abandoned = settings.storage_root / "processing" / f"{held.id}-{held.token}-abandoned"
    abandoned.mkdir(parents=True)
    (abandoned / "private.flac").write_bytes(b"synthetic-private-audio")
    with sessions.begin() as session:
        session.get(Job, key).lease_expires_at = now() + timedelta(seconds=5)
    values = {
        **os.environ,
        "APP_ENV": "test",
        "SECRET_KEY": "synthetic-child-worker-" * 4,
        "DATABASE_URL": settings.database_url,
        "AI_BACKEND": "fixture",
        "PROCESSING_WORKERS": "1",
        "DATABASE_CONNECTION_BUDGET": "9",
        "RECORDING_STORAGE_ROOT": str(settings.storage_root),
    }
    child = subprocess.Popen(
        [sys.executable, "-m", "scripts.run_worker"],
        env=values,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        deadline = time.monotonic() + 15
        complete = False
        while time.monotonic() < deadline:
            with sessions() as session:
                complete = session.get(Job, key).stage == "COMPLETED"
            if complete:
                break
            time.sleep(0.1)
        assert complete, "Fresh worker failed to process its committed fixture job"
        assert not abandoned.exists(), "Expired crash artifacts were not revisited"
    finally:
        child.terminate()
        child.wait(timeout=10)
