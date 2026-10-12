from urllib.parse import urlencode

from fastapi import APIRouter, Depends, Request, Response

from app.components.accounts import service
from app.components.accounts.schemas import (
    ConfirmationRequest,
    EmailRequest,
    LoginRequest,
    ResetRequest,
    SignupRequest,
    StrictInput,
)
from app.libs.dependencies import IdentityDep, SessionDep, ensure_csrf
from app.libs.errors import ApiError
from app.libs.mail import MailMessage, deliver_mail
from app.libs.security import digest_token, issue_csrf, validate_csrf

router = APIRouter(prefix="/v1", dependencies=[Depends(ensure_csrf)])


def cookie(response, name, value, settings, *, http_only=False, max_age=None):
    if max_age is None:
        max_age = 604800 if name == "sessionid" else 31449600
    response.set_cookie(
        name,
        value,
        max_age=max_age,
        path="/",
        secure=settings.cookie_secure,
        httponly=http_only,
        samesite="lax",
    )


def send_link(request, link):
    if link is None:
        return
    title = (
        "Confirm your Archy signup attempt"
        if link.route == "confirm-email"
        else "Reset your Archy password"
    )
    query = {"token": link.token}
    if link.uid:
        query["uid"] = link.uid
    url = f"{request.app.state.settings.frontend_origin}/{link.route}?{urlencode(query)}"
    deliver_mail(
        MailMessage(
            link.email,
            title,
            (
                f"{title}\n\nUse this link only for the request you made. "
                f"If you did not request it, ignore this email.\n\n{url}\n"
            ),
        ),
        request.app.state.settings,
        request.app.state.outbox,
    )


def throttle(request, scope):
    request.app.state.account_limiter.check(
        scope, request.client.host if request.client else "unknown"
    )


@router.get("/auth/csrf")
def csrf(request: Request, response: Response):
    settings = request.app.state.settings
    token = request.cookies.get("csrftoken", "")
    try:
        validate_csrf(token, token, settings.frontend_origin, settings)
    except ApiError:
        token = issue_csrf(settings.secret_key)
    cookie(response, "csrftoken", token, settings)
    return {"csrfToken": token}


@router.post("/auth/signup", status_code=202)
def signup(data: SignupRequest, request: Request, session: SessionDep):
    throttle(request, "signup")
    send_link(request, service.signup(session, data))
    return {"message": "Check your email for the next step."}


@router.post("/auth/confirm-email")
def confirm(data: ConfirmationRequest, session: SessionDep):
    service.confirm_email(session, data.token)
    return {"message": "Email confirmed."}


@router.post("/auth/login")
def login(data: LoginRequest, request: Request, response: Response, session: SessionDep):
    throttle(request, "login")
    credentials = service.login(session, data, request.cookies.get("sessionid", ""))
    settings = request.app.state.settings
    cookie(response, "sessionid", credentials.token, settings, http_only=True)
    cookie(response, "csrftoken", issue_csrf(settings.secret_key), settings)
    return credentials.identity.response()


@router.post("/auth/logout")
def logout(
    data: StrictInput,
    request: Request,
    response: Response,
    identity: IdentityDep,
    session: SessionDep,
):
    service.logout(session, digest_token(request.cookies.get("sessionid", "")))
    settings = request.app.state.settings
    response.delete_cookie(
        "sessionid", path="/", secure=settings.cookie_secure, httponly=True, samesite="lax"
    )
    return {"message": "Signed out."}


@router.post("/auth/password-reset", status_code=202)
def password_reset(data: EmailRequest, request: Request, session: SessionDep):
    throttle(request, "reset")
    send_link(request, service.request_password_reset(session, str(data.email)))
    return {"message": "Check your email for the next step."}


@router.post("/auth/password-reset/confirm")
def reset_confirm(data: ResetRequest, session: SessionDep):
    service.reset_password(session, data)
    return {"message": "Password updated."}


@router.get("/users/me")
def me(identity: IdentityDep):
    return identity.response()
