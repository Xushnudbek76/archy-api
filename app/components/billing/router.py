from typing import Literal
from uuid import UUID

import anyio
from fastapi import APIRouter, Depends, Request
from pydantic import Field

from app.components.accounts.router import throttle
from app.components.accounts.schemas import StrictInput
from app.components.billing import service, worker
from app.libs.dependencies import IdentityDep, SessionDep, ensure_csrf

router = APIRouter(prefix="/v1/billing", dependencies=[Depends(ensure_csrf)])


class CheckoutInput(StrictInput):
    plan: Literal["plus", "pro"]
    requestId: UUID = Field(strict=False)
    consent: Literal["monthly-test-v1"]


class ConfirmInput(StrictInput):
    orderId: str = Field(pattern=r"^archy_[0-9a-f]{32}$")
    customerKey: str = Field(min_length=22, max_length=50)
    authKey: str = Field(min_length=1, max_length=300)


@router.get("/catalog")
def catalog(request: Request):
    return service.catalog(request.app.state.settings)


@router.get("")
def summary(identity: IdentityDep, session: SessionDep):
    return service.summary(session, identity.id)


@router.post("/checkout", status_code=201)
def checkout(data: CheckoutInput, request: Request, identity: IdentityDep, session: SessionDep):
    throttle(request, "billing")
    return service.checkout(session, request.app.state.settings, identity.id, data)


@router.post("/confirm")
async def confirm(data: ConfirmInput, request: Request, identity: IdentityDep):
    throttle(request, "billing")

    def accept():
        with request.app.state.sessions() as session:
            return service.confirm(session, request.app.state.settings, identity.id, data)

    key = await anyio.to_thread.run_sync(accept)
    await anyio.to_thread.run_sync(
        worker.process,
        request.app.state.sessions,
        request.app.state.settings.billing,
        key,
        limiter=request.app.state.billing_limiter,
    )

    def read():
        with request.app.state.sessions() as session:
            return service.order_response(service.owned(session, identity.id, key))

    return await anyio.to_thread.run_sync(read)


@router.get("/orders/{key}")
def order(key: str, identity: IdentityDep, session: SessionDep):
    return service.order_response(service.owned(session, identity.id, key))


@router.post("/cancel")
def cancel(data: StrictInput, identity: IdentityDep, session: SessionDep):
    return service.cancel(session, identity.id)


@router.post("/orders/{key}/reconcile")
async def reconcile(key: str, data: StrictInput, request: Request, identity: IdentityDep):
    throttle(request, "billing")

    def authorize():
        with request.app.state.sessions() as session:
            service.owned(session, identity.id, key)

    await anyio.to_thread.run_sync(authorize)
    await anyio.to_thread.run_sync(
        worker.reconcile,
        request.app.state.sessions,
        request.app.state.settings.billing,
        key,
        limiter=request.app.state.billing_limiter,
    )

    def read():
        with request.app.state.sessions() as session:
            return service.order_response(service.owned(session, identity.id, key))

    return await anyio.to_thread.run_sync(read)
