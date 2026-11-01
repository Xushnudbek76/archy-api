from uuid import UUID

from fastapi import APIRouter, Depends

from app.components.accounts.schemas import StrictInput
from app.components.preferences import service
from app.components.preferences.schemas import FormatInput, ProfilePatch
from app.libs.dependencies import IdentityDep, SessionDep, ensure_csrf

router = APIRouter(prefix="/v1/preferences", dependencies=[Depends(ensure_csrf)])


@router.get("")
def read_profile(identity: IdentityDep, session: SessionDep):
    return service.read_profile(session, identity.id)


@router.patch("")
def update_profile(data: ProfilePatch, identity: IdentityDep, session: SessionDep):
    return service.update_profile(session, identity.id, data)


@router.get("/formats")
def formats(identity: IdentityDep, session: SessionDep):
    return service.list_formats(session, identity.id)


@router.post("/formats", status_code=201)
def create_format(data: FormatInput, identity: IdentityDep, session: SessionDep):
    return service.create_format(session, identity.id, data)


@router.patch("/formats/{key}")
def update_format(key: UUID, data: FormatInput, identity: IdentityDep, session: SessionDep):
    return service.update_format(session, identity.id, key, data)


@router.post("/formats/{key}/remove")
def remove_format(key: UUID, data: StrictInput, identity: IdentityDep, session: SessionDep):
    return service.archive_format(session, identity.id, key)
