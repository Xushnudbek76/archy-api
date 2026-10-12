from uuid import UUID

from fastapi import APIRouter, Request

from app.components.processing import service
from app.libs.dependencies import IdentityDep, SessionDep
from app.libs.errors import ApiError

router = APIRouter(prefix="/v1/recordings")


def query(request):
    if request.query_params:
        raise ApiError(400)


@router.get("/{recording_id}/processing")
def status(recording_id: UUID, request: Request, identity: IdentityDep, session: SessionDep):
    query(request)
    return service.status(session, identity.id, recording_id)


@router.get("/{recording_id}/transcript")
def transcript(recording_id: UUID, request: Request, identity: IdentityDep, session: SessionDep):
    query(request)
    return service.result(session, identity.id, recording_id, "transcript")


@router.get("/{recording_id}/notes")
def notes(recording_id: UUID, request: Request, identity: IdentityDep, session: SessionDep):
    query(request)
    return service.result(session, identity.id, recording_id, "notes")
