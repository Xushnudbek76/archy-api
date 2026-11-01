from uuid import UUID

import anyio
from fastapi import APIRouter, Depends, Request

from app.components.academics import service
from app.components.academics.schemas import (
    ImportConfirm,
    ImportPreview,
    NamedInput,
    TimetableInput,
)
from app.components.accounts.schemas import StrictInput
from app.libs.dependencies import IdentityDep, SessionDep, ensure_csrf
from app.libs.errors import ApiError
from app.libs.workers import run_worker

router = APIRouter(prefix="/v1/academics", dependencies=[Depends(ensure_csrf)])


@router.post("/import/preview")
async def preview_import(data: ImportPreview, request: Request, identity: IdentityDep):
    from app.components.academics.importer import fetch_public, parse_timetable, share_identifier

    identifier = share_identifier(data.url)
    limiter = request.app.state.timetable_import_limiter
    try:
        limiter.acquire_nowait()
    except anyio.WouldBlock:
        raise ApiError(429, retry_after=5) from None
    try:
        return {"courses": await run_worker(lambda: parse_timetable(fetch_public(identifier)))}
    finally:
        limiter.release()


@router.post("/import/confirm", status_code=201)
def confirm_import(data: ImportConfirm, identity: IdentityDep, session: SessionDep):
    from app.components.academics.import_service import confirm_import

    return confirm_import(session, identity.id, data)


@router.get("")
def overview(identity: IdentityDep, session: SessionDep):
    return service.overview(session, identity.id)


@router.post("/terms", status_code=201)
def create_term(data: NamedInput, identity: IdentityDep, session: SessionDep):
    return service.create_term(session, identity.id, data)


@router.patch("/terms/{key}")
def rename_term(key: UUID, data: NamedInput, identity: IdentityDep, session: SessionDep):
    return service.rename_term(session, identity.id, key, data)


@router.post("/terms/{key}/archive")
def archive_term(key: UUID, data: StrictInput, identity: IdentityDep, session: SessionDep):
    return service.archive_term(session, identity.id, key)


@router.post("/timetables", status_code=201)
def create_timetable(data: TimetableInput, identity: IdentityDep, session: SessionDep):
    return service.create_timetable(session, identity.id, data)


@router.patch("/timetables/{key}")
def rename_timetable(key: UUID, data: NamedInput, identity: IdentityDep, session: SessionDep):
    return service.rename_timetable(session, identity.id, key, data)


@router.post("/timetables/{key}/select")
def select_timetable(key: UUID, data: StrictInput, identity: IdentityDep, session: SessionDep):
    return service.select_timetable(session, identity.id, key)


@router.post("/timetables/{key}/primary")
def make_primary(key: UUID, data: StrictInput, identity: IdentityDep, session: SessionDep):
    return service.make_primary(session, identity.id, key)
