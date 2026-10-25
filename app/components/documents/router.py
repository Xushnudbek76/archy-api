from uuid import UUID

from fastapi import APIRouter, Depends, Request
from starlette.datastructures import QueryParams

from app.components.accounts.schemas import StrictInput
from app.components.documents import service
from app.components.documents.schemas import DocumentInput, DocumentPatch
from app.libs.dependencies import IdentityDep, SessionDep, ensure_csrf
from app.libs.errors import ApiError
from app.libs.pagination import page_query

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
