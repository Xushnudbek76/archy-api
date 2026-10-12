from dataclasses import replace
from datetime import timedelta
from uuid import uuid4

import pytest
from sqlalchemy import delete, select

from app.components.accounts.models import User
from app.components.courses.models import Course
from app.components.processing.config import ProcessingSettings
from app.components.processing.models import (
    Job,
    Note,
    ProviderGate,
    Transcript,
    TranscriptChunk,
    now,
)
from app.components.recordings.models import Recording, Upload
from app.database.session import create_engine_for, session_factory
from tests.fastapi.test_storage import audio_bytes


@pytest.fixture
def work(settings, prepared_database):
    settings = replace(
        settings, processing=ProcessingSettings(backend="fixture", workers=1), connection_budget=9
    )
    engine = create_engine_for(settings, worker=True)
    sessions = session_factory(engine)
    owner, course, key, job = (uuid4() for _ in range(4))
    content = audio_bytes()
    path = settings.storage_root / "recordings" / f"{key}.audio"
    path.parent.mkdir(parents=True)
    path.write_bytes(content)
    with sessions.begin() as session:
        session.add(
            User(id=owner, email=f"{owner}@example.com", password="synthetic", is_active=True)
        )
        session.add(Course(id=course, owner_id=owner, title="Synthetic worker course"))
        session.add(
            Upload(
                id=key,
                course_id=course,
                title="Lecture",
                file_name="sample.wav",
                size_bytes=len(content),
                uploaded_bytes=len(content),
                sha256="0" * 64,
                status="ACCEPTED",
                max_duration_seconds=1200,
            )
        )
        session.add(
            Recording(
                id=key,
                upload_id=key,
                course_id=course,
                title="Lecture",
                size_bytes=len(content),
                sha256="0" * 64,
                content_type="audio/wav",
                duration_seconds=1,
            )
        )
        session.add(Job(id=job, recording_id=key, configuration=settings.processing.snapshot()))
    try:
        yield sessions, settings, job
    finally:
        with sessions.begin() as session:
            session.execute(delete(Job).where(Job.id == job))
            session.execute(delete(Recording).where(Recording.id == key))
            session.execute(delete(Upload).where(Upload.id == key))
            session.execute(delete(Course).where(Course.id == course))
            session.execute(delete(User).where(User.id == owner))
            session.execute(delete(ProviderGate).where(ProviderGate.model.like("fixture:%")))
        engine.dispose()


def test_fixture_pipeline_persists_transcript_and_notes_without_repeat_calls(work):
    from app.components.processing.providers import FixtureProvider
    from app.components.processing.worker import run_once

    sessions, settings, job_id = work
    provider = FixtureProvider()
    for _ in range(10):
        run_once(sessions, settings, provider)
        with sessions() as session:
            if session.get(Job, job_id).stage == "COMPLETED":
                break
    with sessions() as session:
        assert session.get(Job, job_id).stage == "COMPLETED"
        assert (
            session.scalar(select(Transcript).where(Transcript.job_id == job_id)).provider
            == "fixture"
        )
        assert session.scalar(select(Note).where(Note.job_id == job_id)).document["overview"]
        assert (
            len(
                session.scalars(
                    select(TranscriptChunk).where(TranscriptChunk.job_id == job_id)
                ).all()
            )
            == 1
        )
    assert run_once(sessions, settings, provider) is False


def test_claim_skips_locked_rows_and_fences_expired_worker(work):
    from app.components.processing.queue import LeaseLost, claim, mutate

    sessions, settings, job_id = work
    with sessions.begin() as held:
        held.scalar(select(Job).where(Job.id == job_id).with_for_update())
        assert claim(sessions) is None
    first = claim(sessions)
    assert first.id == job_id
    assert claim(sessions) is None
    with sessions.begin() as session:
        session.get(Job, job_id).lease_expires_at = now() - timedelta(seconds=1)
    second = claim(sessions)
    assert second.token != first.token
    with pytest.raises(LeaseLost):
        mutate(sessions, first, lambda session, job: setattr(job, "stage", "FAILED"))
    with sessions() as session:
        assert session.get(Job, job_id).stage != "FAILED"


def test_summary_retry_keeps_transcription_and_saved_parts(work):
    from app.components.processing.providers import FixtureProvider, ProviderFailure
    from app.components.processing.worker import run_once

    sessions, settings, job_id = work

    class SummaryFailure(FixtureProvider):
        def summarize(self, source, language, config):
            raise ProviderFailure("provider_unavailable")

    provider = SummaryFailure()
    for _ in range(4):
        run_once(sessions, settings, provider)
    with sessions() as session:
        assert session.scalar(select(Transcript).where(Transcript.job_id == job_id)) is not None
        job = session.get(Job, job_id)
        assert job.summary_attempts == 1
        assert job.stage == "SUMMARIZING"
    with sessions.begin() as session:
        session.get(Job, job_id).available_at = now()
    for _ in range(5):
        run_once(sessions, settings, FixtureProvider())
    with sessions() as session:
        assert session.get(Job, job_id).stage == "COMPLETED"
        assert (
            len(
                session.scalars(
                    select(TranscriptChunk).where(TranscriptChunk.job_id == job_id)
                ).all()
            )
            == 1
        )


def test_quota_wait_releases_lease_and_does_not_spend_failure_attempt(work):
    from app.components.processing.providers import FixtureProvider, ProviderFailure
    from app.components.processing.worker import run_once

    sessions, settings, job_id = work

    class Quota(FixtureProvider):
        def transcribe(self, path, config):
            raise ProviderFailure("quota_wait", retry_after=3600, quota=True)

    run_once(sessions, settings, Quota())
    with sessions() as session:
        job = session.get(Job, job_id)
        assert job.lease_token is None
        assert job.transcription_attempts == 0
        assert job.deferrals == 1
        assert job.available_at > now() + timedelta(seconds=3500)
    assert run_once(sessions, settings, Quota()) is False


def test_provider_pacing_defers_without_leaving_a_live_lease(work):
    from app.components.processing.providers import FixtureProvider
    from app.components.processing.worker import run_once

    sessions, settings, job_id = work

    class Paced(FixtureProvider):
        name = "groq"

    run_once(sessions, settings, Paced())
    with sessions.begin() as session:
        session.execute(delete(TranscriptChunk).where(TranscriptChunk.job_id == job_id))
    run_once(sessions, settings, Paced())
    with sessions() as session:
        job = session.get(Job, job_id)
        assert job.lease_token is None and job.available_at > now()
        assert job.transcription_attempts == 0
    with sessions.begin() as session:
        session.execute(delete(ProviderGate).where(ProviderGate.model == "whisper-large-v3-turbo"))
