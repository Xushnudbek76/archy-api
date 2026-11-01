from fastapi import APIRouter, Depends, Request, Response
from pydantic import Field

from app.components.accounts.router import cookie, throttle
from app.components.accounts.schemas import StrictInput
from app.components.oauth import service
from app.components.oauth.provider import PROVIDERS, credentials
from app.libs.dependencies import SessionDep, ensure_csrf
from app.libs.errors import ApiError
from app.libs.security import issue_csrf

router = APIRouter(prefix="/v1/oauth")


class StartInput(StrictInput):
    returnTo: str = Field(default="/dashboard", max_length=100)


class FinishInput(StrictInput):
    code: str = Field(min_length=1, max_length=4096)
    state: str = Field(min_length=1, max_length=128)


@router.get("/providers")
def providers(request: Request):
    items = []
    for name in PROVIDERS:
        try:
            credentials(request.app.state.settings, name)
            items.append(name)
        except ApiError:
            pass
    return {"items": items}


@router.post("/{name}/start", dependencies=[Depends(ensure_csrf)])
def start(name: str, data: StartInput, request: Request, response: Response, session: SessionDep):
    throttle(request, "login")
    settings = request.app.state.settings
    url, browser = service.begin(session, settings, name, data.returnTo)
    response.set_cookie(
        "oauth_flow",
        browser,
        max_age=600,
        path="/",
        httponly=True,
        secure=settings.cookie_secure,
        samesite="none" if name == "apple" else "lax",
    )
    return {"url": url}


@router.post("/{name}/finish")
def finish(name: str, data: FinishInput, request: Request, response: Response, session: SessionDep):
    throttle(request, "login")
    settings = request.app.state.settings
    result, return_to = service.finish(
        session,
        settings,
        name,
        data.code,
        data.state,
        request.cookies.get("oauth_flow", ""),
        request.cookies.get("sessionid", ""),
    )
    cookie(response, "sessionid", result.token, settings, http_only=True)
    cookie(response, "csrftoken", issue_csrf(settings.secret_key), settings)
    response.delete_cookie(
        "oauth_flow",
        path="/",
        secure=settings.cookie_secure,
        httponly=True,
        samesite="none" if name == "apple" else "lax",
    )
    return {"returnTo": return_to}
