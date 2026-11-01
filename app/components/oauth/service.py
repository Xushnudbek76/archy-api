import hmac
import secrets
from datetime import timedelta

from email_validator import EmailNotValidError, validate_email
from sqlalchemy import delete, func, select, text
from sqlalchemy.exc import IntegrityError

from app.components.accounts.models import AccountSession, User, now
from app.components.accounts.service import SessionCredentials, identity
from app.components.oauth import provider
from app.components.oauth.models import OAuthIdentity, OAuthState
from app.libs.errors import ApiError
from app.libs.security import digest_token, hash_password

DESTINATIONS = {
    "/dashboard",
    "/documents",
    "/record",
    "/recordings",
    "/courses",
    "/timetable",
    "/settings",
    "/settings/billing",
    "/pricing",
}


def begin(session, settings, name, return_to):
    provider.credentials(settings, name)
    token, browser, nonce, verifier = (secrets.token_urlsafe(32) for _ in range(4))
    session.execute(delete(OAuthState).where(OAuthState.expires_at < now()))
    session.add(
        OAuthState(
            digest=digest_token(token),
            browser_digest=digest_token(browser),
            provider=name,
            nonce=nonce,
            verifier=verifier,
            return_to=return_to if return_to in DESTINATIONS else "/dashboard",
            expires_at=now() + timedelta(minutes=10),
        )
    )
    session.commit()
    return provider.authorization(settings, name, token, nonce, verifier), browser


def consume(session, settings, name, state, browser):
    provider.credentials(settings, name)
    row = session.scalar(
        select(OAuthState).where(OAuthState.digest == digest_token(state)).with_for_update()
    )
    if (
        not row
        or row.provider != name
        or row.consumed_at
        or row.expires_at <= now()
        or not browser
        or not hmac.compare_digest(row.browser_digest, digest_token(browser))
    ):
        raise ApiError(400, "oauth_failed", "This sign-in link expired. Start again.")
    result = (row.nonce, row.verifier, row.return_to)
    row.consumed_at = now()
    session.commit()
    return result


def finish(session, settings, name, code, state, browser, old_session):
    nonce, verifier, return_to = consume(session, settings, name, state, browser)
    claims = provider.exchange(settings, name, code, nonce, verifier)
    try:
        lock = int(digest_token(name + ":" + claims["sub"])[:15], 16)
        session.execute(text("SELECT pg_advisory_xact_lock(:key)"), {"key": lock})
        link = session.scalar(
            select(OAuthIdentity).where(
                OAuthIdentity.provider == name, OAuthIdentity.subject == claims["sub"]
            )
        )
        if link:
            user = session.scalar(select(User).where(User.id == link.owner_id).with_for_update())
            if not user or not user.is_active:
                raise ApiError(403)
        else:
            if claims.get("email_verified") not in (True, "true"):
                raise ApiError(400, "verified_email_required", "A verified email is required.")
            try:
                email = validate_email(
                    claims.get("email", ""), check_deliverability=False
                ).normalized.lower()
            except EmailNotValidError:
                raise ApiError(
                    400, "verified_email_required", "A verified email is required."
                ) from None
            if session.scalar(select(User.id).where(func.lower(User.email) == email)):
                raise ApiError(
                    409, "account_link_required", "Use your existing sign-in method for this email."
                )
            display_name = claims.get("name", "")
            user = User(
                email=email,
                password=hash_password(secrets.token_urlsafe(48)),
                display_name=display_name[:100] if isinstance(display_name, str) else "",
                is_active=True,
                email_confirmed_at=now(),
            )
            session.add(user)
            session.flush()
            session.add(OAuthIdentity(owner_id=user.id, provider=name, subject=claims["sub"]))
        session.execute(
            delete(AccountSession).where(AccountSession.digest == digest_token(old_session))
        )
        token = secrets.token_urlsafe(32)
        session.add(
            AccountSession(
                user_id=user.id, digest=digest_token(token), expires_at=now() + timedelta(days=7)
            )
        )
        user.last_login = now()
        result = SessionCredentials(identity(user), token)
        session.commit()
        return result, return_to
    except IntegrityError:
        session.rollback()
        raise ApiError(
            409, "account_link_required", "Use your existing sign-in method for this email."
        ) from None
