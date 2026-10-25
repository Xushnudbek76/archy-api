from uuid import UUID

from fastapi import APIRouter, Depends

from app.components.accounts.schemas import StrictInput
from app.components.tutor import service
from app.libs.dependencies import IdentityDep, SessionDep, ensure_csrf

router = APIRouter(dependencies=[Depends(ensure_csrf)])


@router.post("/v1/documents/{document_id}/conversations", status_code=201)
def create(document_id: UUID, data: StrictInput, identity: IdentityDep, session: SessionDep):
    return service.create_conversation(session, identity.id, document_id)


@router.get("/v1/documents/{document_id}/conversations")
def listing(document_id: UUID, identity: IdentityDep, session: SessionDep):
    return service.list_conversations(session, identity.id, document_id)


@router.get("/v1/conversations/{conversation_id}")
def read(conversation_id: UUID, identity: IdentityDep, session: SessionDep):
    return service.read_conversation(session, identity.id, conversation_id)
