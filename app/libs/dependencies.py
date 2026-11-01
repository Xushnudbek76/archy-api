from typing import Annotated

from fastapi import Depends, Request
from sqlalchemy.orm import Session

from app.components.accounts.service import AccountIdentity


def get_session(request: Request):
    with request.app.state.sessions() as session:
        yield session


def ensure_csrf(request: Request):
    from app.libs.security import validate_csrf

    if request.method not in {"GET", "HEAD", "OPTIONS"}:
        validate_csrf(
            request.cookies.get("csrftoken", ""),
            request.headers.get("X-CSRFToken", ""),
            request.headers.get("Origin", ""),
            request.app.state.settings,
        )


def request_identity(session, request: Request):
    from app.components.accounts.service import current_identity
    from app.components.demo.constants import DEMO_USER_ID
    from app.libs.errors import ApiError

    identity = current_identity(session, request.cookies.get("sessionid", ""))
    expected = request.headers.get("X-Workspace-User")
    if expected is not None and expected != str(identity.id):
        raise ApiError(403, "account_changed", "Your account changed. Reload this workspace.")
    if identity.id == DEMO_USER_ID and request.url.path != "/v1/auth/logout":
        if not request.app.state.settings.demo_enabled:
            raise ApiError(403)
        if request.method not in {"GET", "HEAD", "OPTIONS"}:
            raise ApiError(403, "demo_read_only", "The sample workspace is read-only.")
    return identity


def get_identity(request: Request):
    with request.app.state.sessions() as session:
        return request_identity(session, request)


SessionDep = Annotated[Session, Depends(get_session)]
IdentityDep = Annotated[AccountIdentity, Depends(get_identity)]
