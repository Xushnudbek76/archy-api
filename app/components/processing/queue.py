import threading
import uuid
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import timedelta

from sqlalchemy import or_, select, update

from app.components.processing.config import ProcessingSettings
from app.components.processing.models import Job, now


class LeaseLost(Exception):
    pass


@dataclass(frozen=True)
class Claim:
    id: uuid.UUID
    recording_id: uuid.UUID
    token: uuid.UUID
    config: ProcessingSettings


def claim(sessions):
    with sessions.begin() as session:
        job = session.scalar(
            select(Job)
            .where(
                Job.stage.not_in(("COMPLETED", "FAILED")),
                Job.available_at <= now(),
                or_(Job.lease_expires_at.is_(None), Job.lease_expires_at <= now()),
            )
            .order_by(Job.available_at, Job.created_at, Job.id)
            .with_for_update(skip_locked=True)
            .limit(1)
        )
        if job is None:
            return None
        config = ProcessingSettings(**job.configuration)
        job.lease_token = uuid.uuid4()
        job.lease_expires_at = now() + timedelta(seconds=config.lease_seconds)
        if job.stage == "QUEUED":
            job.stage = "TRANSCRIBING"
        job.updated_at = now()
        return Claim(job.id, job.recording_id, job.lease_token, config)


def mutate(sessions, held, function):
    with sessions.begin() as session:
        job = session.scalar(
            select(Job)
            .where(Job.id == held.id, Job.lease_token == held.token, Job.lease_expires_at > now())
            .with_for_update()
        )
        if job is None:
            raise LeaseLost
        value = function(session, job)
        job.updated_at = now()
        return value


def release(job, delay=0):
    job.available_at = now() + timedelta(seconds=delay)
    job.lease_token = None
    job.lease_expires_at = None


@contextmanager
def heartbeat(sessions, held):
    stopped, lost = threading.Event(), threading.Event()

    def renew():
        while not stopped.wait(held.config.heartbeat_seconds):
            try:
                with sessions.begin() as session:
                    result = session.execute(
                        update(Job)
                        .where(
                            Job.id == held.id,
                            Job.lease_token == held.token,
                            Job.lease_expires_at > now(),
                        )
                        .values(
                            lease_expires_at=now() + timedelta(seconds=held.config.lease_seconds)
                        )
                    )
                    if result.rowcount != 1:
                        lost.set()
                        return
            except Exception:
                lost.set()
                return

    thread = threading.Thread(target=renew, daemon=True)
    thread.start()
    try:
        yield lost
    finally:
        stopped.set()
        thread.join(timeout=7)
