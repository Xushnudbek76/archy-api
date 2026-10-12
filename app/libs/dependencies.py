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


def get_identity(request: Request):
    from app.components.accounts.service import current_identity

    with request.app.state.sessions() as session:
        return current_identity(session, request.cookies.get("sessionid", ""))


SessionDep = Annotated[Session, Depends(get_session)]
IdentityDep = Annotated[AccountIdentity, Depends(get_identity)]
