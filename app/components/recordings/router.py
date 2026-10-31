from uuid import UUID

import anyio
from fastapi import APIRouter, Depends, Request, Response

from app.components.accounts.schemas import StrictInput
from app.components.recordings import service
from app.components.recordings.playback import audio_response
from app.components.recordings.schemas import UploadInput
from app.libs.body import receive_body
from app.libs.dependencies import IdentityDep, SessionDep, ensure_csrf, request_identity
from app.libs.errors import ApiError
from app.libs.pagination import page_query
from app.libs.workers import run_worker

router = APIRouter(prefix="/v1", dependencies=[Depends(ensure_csrf)])


def owned_unit(request, function, *args, **kwargs):
    with request.app.state.sessions() as session:
        identity = request_identity(session, request)
        return function(session, identity.id, *args, **kwargs)


@router.get("/uploads")
def uploads(request: Request, identity: IdentityDep, session: SessionDep):
    return service.list_uploads(session, identity.id, page_query(request.query_params))


@router.post("/uploads")
def admit(
    data: UploadInput,
    request: Request,
    response: Response,
    identity: IdentityDep,
    session: SessionDep,
):
    upload, created = service.admit_upload(
        session,
        identity.id,
        data,
        request.app.state.settings.storage_root,
        request.app.state.settings.max_audio_duration_seconds,
    )
    response.status_code = 201 if created else 200
    return upload


@router.get("/uploads/policy")
def policy(request: Request, identity: IdentityDep):
    page_query(request.query_params)
    return {"maxDurationSeconds": request.app.state.settings.max_audio_duration_seconds}


@router.get("/uploads/{upload_id}")
def read(upload_id: UUID, identity: IdentityDep, session: SessionDep):
    return service.read_upload(session, identity.id, upload_id)


@router.patch("/uploads/{upload_id}/chunks")
async def chunks(upload_id: UUID, request: Request):
    await run_worker(owned_unit, request, service.read_upload, upload_id)
    offset = request.headers.get("Upload-Offset", "")
    if not offset.isascii() or not offset.isdigit() or len(offset) > 16:
        raise ApiError(400)
    if (
        request.headers.get("Content-Type", "").split(";")[0].strip().lower()
        != "application/octet-stream"
    ):
        raise ApiError(415, "invalid_chunk", "Send a binary audio chunk.")
    limiter = request.app.state.chunk_limiter
    try:
        limiter.acquire_nowait()
    except anyio.WouldBlock:
        raise ApiError(429, retry_after=2) from None
    try:
        body = await receive_body(request, service.CHUNK_BYTES)
        return await run_worker(
            owned_unit,
            request,
            service.receive_chunk,
            upload_id,
            int(offset),
            body,
            request.app.state.settings.storage_root,
        )
    finally:
        limiter.release()


@router.post("/uploads/{upload_id}/complete")
def complete(
    upload_id: UUID,
    data: StrictInput,
    request: Request,
    identity: IdentityDep,
    session: SessionDep,
):
    upload = service.complete_upload(
        session,
        identity.id,
        upload_id,
        request.app.state.settings.storage_root,
        request.app.state.settings.processing,
    )
    if upload.status == "FAILED":
        raise ApiError(400, upload.errorCode, service.ERRORS[upload.errorCode])
    return upload


@router.post("/uploads/{upload_id}/cancel")
def cancel(
    upload_id: UUID,
    data: StrictInput,
    request: Request,
    identity: IdentityDep,
    session: SessionDep,
):
    return service.cancel_upload(
        session, identity.id, upload_id, request.app.state.settings.storage_root
    )


@router.get("/recordings")
def recordings(request: Request, identity: IdentityDep, session: SessionDep):
    return service.list_recordings(session, identity.id, page_query(request.query_params))


@router.api_route("/recordings/{recording_id}/audio", methods=["GET", "HEAD"])
async def audio(recording_id: UUID, request: Request):
    metadata = await run_worker(
        owned_unit,
        request,
        service.authorize_audio,
        recording_id,
        request.app.state.settings.storage_root,
    )
    return await audio_response(metadata, request)
