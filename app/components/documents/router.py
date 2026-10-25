from uuid import UUID

import anyio
from fastapi import APIRouter, Depends, Request
from starlette.datastructures import QueryParams

from app.components.accounts.schemas import StrictInput
from app.components.accounts.service import current_identity
from app.components.documents import service
from app.components.documents.extraction import extract_pdf
from app.components.documents.pdf import MAX_PDF_BYTES, file_name, pdf_response, validate_pdf
from app.components.documents.schemas import DocumentInput, DocumentPatch
from app.libs.body import receive_body
from app.libs.dependencies import IdentityDep, SessionDep, ensure_csrf
from app.libs.errors import ApiError
from app.libs.pagination import page_query
from app.libs.workers import run_worker

router = APIRouter(prefix="/v1/documents", dependencies=[Depends(ensure_csrf)])


@router.get("")
def documents(request: Request, identity: IdentityDep, session: SessionDep):
    query = request.query_params
    if set(query) - {"page", "q", "courseId"} or any(len(query.getlist(key)) != 1 for key in query):
        raise ApiError(400)
    if len(query.get("q", "")) > 100:
        raise ApiError(400)
    try:
        course_id = UUID(query["courseId"]) if "courseId" in query else None
    except ValueError:
        raise ApiError(400) from None
    page = page_query(QueryParams({"page": query.get("page", "1")}))
    return service.list_documents(session, identity.id, page, query.get("q", ""), course_id)


@router.post("", status_code=201)
def create(data: DocumentInput, identity: IdentityDep, session: SessionDep):
    return service.create_document(session, identity.id, data)


@router.get("/{document_id}")
def read(document_id: UUID, identity: IdentityDep, session: SessionDep):
    return service.read_document(session, identity.id, document_id)


@router.patch("/{document_id}")
def update(document_id: UUID, data: DocumentPatch, identity: IdentityDep, session: SessionDep):
    return service.update_document(session, identity.id, document_id, data)


@router.post("/{document_id}/archive")
def archive(document_id: UUID, data: StrictInput, identity: IdentityDep, session: SessionDep):
    return service.archive_document(session, identity.id, document_id)


def owned_unit(request, function, *args):
    with request.app.state.sessions() as session:
        identity = current_identity(session, request.cookies.get("sessionid", ""))
        return function(session, identity.id, *args)


@router.post("/{document_id}/pdf")
async def upload_pdf(document_id: UUID, request: Request):
    await run_worker(owned_unit, request, service.authorize_upload, document_id)
    if request.headers.get("content-type", "").split(";")[0].strip().lower() != "application/pdf":
        raise ApiError(415, "invalid_pdf", "Send a PDF file.")
    name = file_name(request.headers.get("x-file-name", ""))
    limiter = request.app.state.pdf_limiter
    try:
        limiter.acquire_nowait()
    except anyio.WouldBlock:
        raise ApiError(429, retry_after=2) from None
    try:
        body = await receive_body(request, MAX_PDF_BYTES)
        validate_pdf(body)
        extracted = await run_worker(extract_pdf, body)
        return await run_worker(
            owned_unit,
            request,
            service.save_pdf,
            document_id,
            body,
            name,
            extracted,
            request.app.state.settings.storage_root,
        )
    finally:
        limiter.release()


@router.api_route("/{document_id}/pdf", methods=["GET", "HEAD"])
async def download_pdf(document_id: UUID, request: Request):
    metadata = await run_worker(
        owned_unit,
        request,
        service.authorize_pdf,
        document_id,
        request.app.state.settings.storage_root,
    )
    return await pdf_response(metadata, request)


@router.get("/{document_id}/sources")
def sources(document_id: UUID, identity: IdentityDep, session: SessionDep):
    from app.components.documents.sources import document_sources

    return {"items": document_sources(session, identity.id, document_id)}
