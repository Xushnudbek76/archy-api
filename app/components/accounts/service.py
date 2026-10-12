import base64
import secrets
from dataclasses import dataclass
from datetime import timedelta
from uuid import UUID

from sqlalchemy import delete, func, select, update
from sqlalchemy.exc import IntegrityError

from app.components.accounts.models import AccountSession, ActionToken, SignupAttempt, User, now
from app.libs.errors import ApiError
from app.libs.security import (
    digest_token,
    hash_password,
    needs_password_upgrade,
    validate_password,
    verify_password,
)

DUMMY_HASH = hash_password("synthetic dummy credential never used for login")


@dataclass(frozen=True)
class AccountIdentity:
    id: UUID
    email: str
    display_name: str
    is_staff: bool
    is_active: bool

    def response(self):
        return {
            "id": str(self.id),
            "email": self.email,
            "displayName": self.display_name,
            "role": "ADMIN" if self.is_staff else "USER",
        }


@dataclass(frozen=True)
class SessionCredentials:
    identity: AccountIdentity
    token: str


@dataclass(frozen=True)
class AccountLink:
    email: str
    route: str
    token: str
    uid: str = ""


def identity(user):
    return AccountIdentity(user.id, user.email, user.display_name, user.is_staff, user.is_active)


def current_identity(session, session_token):
    if not session_token or len(session_token) > 128:
        raise ApiError(403)
    user = session.scalars(
        select(User)
        .join(AccountSession, AccountSession.user_id == User.id)
        .where(
            AccountSession.digest == digest_token(session_token),
            AccountSession.expires_at > now(),
            User.is_active.is_(True),
        )
    ).first()
    if user is None:
        raise ApiError(403)
    return identity(user)


def issue_action(session, user, purpose, attempt=None):
    secret = secrets.token_urlsafe(32)
    session.add(
        ActionToken(
            user_id=user.id,
            signup_attempt_id=attempt.id if attempt else None,
            digest=digest_token(secret),
            purpose=purpose,
            expires_at=now() + timedelta(hours=24 if purpose == "confirm" else 1),
        )
    )
    return AccountLink(
        user.email,
        "confirm-email" if purpose == "confirm" else "reset-password",
        secret,
        base64.urlsafe_b64encode(str(user.id).encode()).decode().rstrip("=")
        if purpose == "reset"
        else "",
    )


def signup(session, data):
    encoded = hash_password(data.password)
    user = session.scalars(
        select(User).where(func.lower(User.email) == str(data.email)).with_for_update()
    ).first()
    created = False
    if user is None:
        try:
            with session.begin_nested():
                user = User(email=str(data.email), password="!unusable")
                session.add(user)
                session.flush()
                created = True
        except IntegrityError:
            user = session.scalars(
                select(User).where(func.lower(User.email) == str(data.email)).with_for_update()
            ).one()
    pending = (
        created
        or session.scalar(select(SignupAttempt.id).where(SignupAttempt.user_id == user.id).limit(1))
        is not None
    )
    if not pending or user.is_active or user.email_confirmed_at is not None:
        session.commit()
        return None
    attempt = SignupAttempt(user_id=user.id, password_hash=encoded, display_name=data.displayName)
    session.add(attempt)
    session.flush()
    link = issue_action(session, user, "confirm", attempt)
    session.commit()
    return link


def lock_action(session, raw, purpose):
    if not raw or len(raw) > 128:
        raise ApiError(400)
    token = session.scalars(
        select(ActionToken).where(
            ActionToken.digest == digest_token(raw), ActionToken.purpose == purpose
        )
    ).first()
    if token is None:
        raise ApiError(400)
    user = session.scalars(select(User).where(User.id == token.user_id).with_for_update()).one()
    token = session.scalars(
        select(ActionToken)
        .where(ActionToken.id == token.id)
        .with_for_update()
        .execution_options(populate_existing=True)
    ).one()
    if token.consumed_at is not None or token.expires_at <= now():
        raise ApiError(400)
    return user, token


def confirm_email(session, token):
    user, action = lock_action(session, token, "confirm")
    attempt = (
        session.get(SignupAttempt, action.signup_attempt_id) if action.signup_attempt_id else None
    )
    if (
        user.is_active
        or user.email_confirmed_at is not None
        or not attempt
        or attempt.user_id != user.id
    ):
        raise ApiError(400)
    user.password = attempt.password_hash
    user.display_name = attempt.display_name
    user.is_active = True
    user.email_confirmed_at = user.updated_at = now()
    action.consumed_at = now()
    session.flush()
    session.execute(delete(SignupAttempt).where(SignupAttempt.user_id == user.id))
    session.commit()


def login(session, data, old_token=""):
    user = session.scalars(
        select(User).where(func.lower(User.email) == str(data.email)).with_for_update()
    ).first()
    valid = verify_password(data.password, user.password if user else DUMMY_HASH)
    if not user or not valid or not user.is_active:
        session.rollback()
        raise ApiError(403)
    if needs_password_upgrade(user.password):
        user.password = hash_password(data.password)
        user.updated_at = now()
    if old_token:
        session.execute(
            delete(AccountSession).where(AccountSession.digest == digest_token(old_token))
        )
    secret = secrets.token_urlsafe(32)
    session.add(
        AccountSession(
            user_id=user.id, digest=digest_token(secret), expires_at=now() + timedelta(days=7)
        )
    )
    user.last_login = now()
    result = SessionCredentials(identity(user), secret)
    session.commit()
    return result


def logout(session, session_digest):
    session.execute(delete(AccountSession).where(AccountSession.digest == session_digest))
    session.commit()


def request_password_reset(session, email):
    user = session.scalars(
        select(User)
        .where(func.lower(User.email) == str(email), User.is_active.is_(True))
        .with_for_update()
    ).first()
    link = (
        issue_action(session, user, "reset") if user and not user.password.startswith("!") else None
    )
    session.commit()
    return link


def invalidate_reset_links(session, user_id):
    session.execute(
        update(ActionToken)
        .where(
            ActionToken.user_id == user_id,
            ActionToken.purpose == "reset",
            ActionToken.consumed_at.is_(None),
        )
        .values(consumed_at=now())
    )


def reset_password(session, data):
    try:
        identifier = UUID(base64.urlsafe_b64decode(data.uid + "=" * (-len(data.uid) % 4)).decode())
    except (ValueError, UnicodeDecodeError):
        raise ApiError(400) from None
    user, action = lock_action(session, data.token, "reset")
    if user.id != identifier or not user.is_active:
        raise ApiError(400)
    validate_password(data.password, user.email)
    user.password = hash_password(data.password)
    user.updated_at = now()
    invalidate_reset_links(session, user.id)
    session.execute(delete(AccountSession).where(AccountSession.user_id == user.id))
    session.commit()
