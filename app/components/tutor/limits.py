import math
from datetime import timedelta

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert

from app.components.accounts.models import now
from app.components.processing.models import ProviderGate
from app.components.tutor.models import Generation, Usage
from app.libs.errors import ApiError


def gate(session, key):
    session.execute(
        insert(ProviderGate)
        .values(model=key, available_at=now() - timedelta(seconds=1))
        .on_conflict_do_nothing()
    )
    return session.scalar(select(ProviderGate).where(ProviderGate.model == key).with_for_update())


def reserve(session, owner_id, provider, *, has_sources):
    # One persisted lock serializes claims across API workers without a long-lived connection.
    gate(session, "tutor:capacity")
    current = now()
    if has_sources:
        quota = gate(session, "tutor:quota:" + provider)
        wait = math.ceil((quota.available_at - current).total_seconds())
        if wait > 0:
            raise ApiError(
                429,
                "quota_wait",
                "The tutor provider is cooling down. Try later.",
                retry_after=wait,
            )
    active = session.scalar(
        select(func.count())
        .select_from(Generation)
        .where(Generation.status == "active", Generation.lease_expires_at > current)
    )
    if active >= 2:
        raise ApiError(429, "tutor_busy", "The tutor is busy. Try again shortly.", retry_after=5)
    usage = session.get(Usage, owner_id)
    if usage is None:
        usage = Usage(owner_id=owner_id, window_started_at=current, attempts=0)
        session.add(usage)
    if usage.window_started_at + timedelta(seconds=60) <= current:
        usage.window_started_at, usage.attempts = current, 0
    if usage.attempts >= 10:
        wait = max(
            1,
            math.ceil((usage.window_started_at + timedelta(seconds=60) - current).total_seconds()),
        )
        raise ApiError(
            429, "tutor_rate_limit", "Too many tutor requests. Try again later.", retry_after=wait
        )
    usage.attempts += 1


def cooldown(session, provider, seconds):
    row = gate(session, "tutor:quota:" + provider)
    row.available_at = max(row.available_at, now() + timedelta(seconds=min(86400, max(1, seconds))))
    session.commit()
