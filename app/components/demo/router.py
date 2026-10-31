from fastapi import APIRouter, Depends, Request, Response

from app.components.accounts.router import cookie, throttle
from app.components.accounts.schemas import StrictInput
from app.components.demo.service import demo_user, open_session
from app.libs.dependencies import SessionDep, ensure_csrf
from app.libs.security import issue_csrf

router = APIRouter(prefix="/v1/demo", dependencies=[Depends(ensure_csrf)])


@router.get("")
def availability(request: Request, session: SessionDep):
    enabled = request.app.state.settings.demo_enabled
    return {"available": enabled and demo_user(session) is not None}


@router.post("/session")
def enter(data: StrictInput, request: Request, response: Response, session: SessionDep):
    throttle(request, "demo")
    settings = request.app.state.settings
    credentials = open_session(session, settings, request.cookies.get("sessionid", ""))
    cookie(response, "sessionid", credentials.token, settings, http_only=True, max_age=900)
    cookie(response, "csrftoken", issue_csrf(settings.secret_key), settings)
    return credentials.identity.response()
