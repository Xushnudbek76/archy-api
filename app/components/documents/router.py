from uuid import UUID

from fastapi import APIRouter, Depends, Request

from app.components.documents import service
from app.components.documents.schemas import DocumentInput
from app.libs.dependencies import IdentityDep, SessionDep, ensure_csrf
from app.libs.pagination import page_query

router = APIRouter(prefix="/v1/documents", dependencies=[Depends(ensure_csrf)])


@router.get("")
def documents(request: Request, identity: IdentityDep, session: SessionDep):
    return service.list_documents(session, identity.id, page_query(request.query_params))


@router.post("", status_code=201)
def create(data: DocumentInput, identity: IdentityDep, session: SessionDep):
    return service.create_document(session, identity.id, data)


@router.get("/{document_id}")
def read(document_id: UUID, identity: IdentityDep, session: SessionDep):
    return service.read_document(session, identity.id, document_id)
