import secrets
from datetime import timedelta

from sqlalchemy import delete, func, select

from app.components.accounts.models import AccountSession, User, now
from app.components.accounts.service import SessionCredentials, current_identity, identity
from app.components.demo.constants import DEMO_EMAIL, DEMO_USER_ID
from app.libs.errors import ApiError
from app.libs.security import digest_token


def demo_user(session, *, locked=False):
    query = select(User).where(
        User.id == DEMO_USER_ID,
        User.email == DEMO_EMAIL,
        User.is_active.is_(True),
        User.is_staff.is_(False),
        User.is_superuser.is_(False),
    )
    return session.scalar(query.with_for_update() if locked else query)


def open_session(session, settings, old_token):
    if not settings.demo_enabled:
        raise ApiError(404)
    try:
        previous = current_identity(session, old_token)
    except ApiError:
        previous = None
    if previous and previous.id != DEMO_USER_ID:
        raise ApiError(409, "already_signed_in", "Continue in your existing workspace.")
    user = demo_user(session, locked=True)
    if user is None:
        raise ApiError(503, "demo_unavailable", "The demo has not been prepared yet.")
    session.execute(
        delete(AccountSession).where(
            AccountSession.user_id == DEMO_USER_ID,
            (AccountSession.expires_at <= now())
            | (AccountSession.digest == digest_token(old_token)),
        )
    )
    count = session.scalar(
        select(func.count())
        .select_from(AccountSession)
        .where(AccountSession.user_id == DEMO_USER_ID)
    )
    if count >= 100:
        raise ApiError(429, "demo_busy", "The demo is busy. Try again shortly.", retry_after=60)
    secret = secrets.token_urlsafe(32)
    session.add(
        AccountSession(
            user_id=DEMO_USER_ID,
            digest=digest_token(secret),
            expires_at=now() + timedelta(minutes=15),
        )
    )
    session.commit()
    return SessionCredentials(identity(user), secret)
