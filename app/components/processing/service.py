from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert

from app.components.courses.models import Course
from app.components.processing.config import ProcessingSettings
from app.components.processing.models import Job, Note, Transcript
from app.components.recordings.models import Recording
from app.libs.errors import ApiError


def enqueue(session, upload, configuration=None):
    if upload.max_duration_seconds is not None:
        session.execute(
            insert(Job)
            .values(
                recording_id=upload.id,
                configuration=(configuration or ProcessingSettings()).snapshot(),
            )
            .on_conflict_do_nothing(index_elements=["recording_id"])
        )


def owned_job(session, owner, recording_id):
    record = session.scalar(
        select(Recording.id)
        .join(Course, Course.id == Recording.course_id)
        .where(Recording.id == recording_id, Course.owner_id == owner)
    )
    if record is None:
        raise ApiError(404)
    return session.scalar(select(Job).where(Job.recording_id == recording_id))


def status(session, owner, recording_id):
    job = owned_job(session, owner, recording_id)
    if job is None:
        return {
            "status": "unavailable",
            "language": None,
            "transcriptAvailable": False,
            "notesAvailable": False,
            "errorCode": "",
            "deferred": False,
            "updatedAt": None,
        }
    transcript = session.scalar(select(Transcript).where(Transcript.job_id == job.id))
    note = session.scalar(select(Note.id).where(Note.job_id == job.id))
    from app.components.processing.models import now

    return {
        "status": "summarizing" if job.stage == "TRANSCRIBED" else job.stage.lower(),
        "language": transcript.language if transcript else None,
        "transcriptAvailable": transcript is not None,
        "notesAvailable": note is not None,
        "errorCode": job.error_code,
        "deferred": job.available_at > now(),
        "updatedAt": job.updated_at.isoformat(),
    }


def result(session, owner, recording_id, kind):
    job = owned_job(session, owner, recording_id)
    model = Transcript if kind == "transcript" else Note
    row = session.scalar(select(model).where(model.job_id == job.id)) if job else None
    if row is None:
        return {"available": False}
    data = {"text": row.text, "segments": row.segments} if kind == "transcript" else row.document
    return {
        "available": True,
        "language": row.language,
        "provider": row.provider,
        "model": row.model,
        "data": data,
    }
