from uuid import UUID

from fastapi import APIRouter, Depends, Request
from starlette.responses import StreamingResponse

from app.components.accounts.schemas import StrictInput
from app.components.documents.router import owned_unit
from app.components.tutor import service, turns
from app.components.tutor.schemas import MessageInput
from app.components.tutor.streaming import answer_events
from app.libs.dependencies import IdentityDep, SessionDep, ensure_csrf
from app.libs.workers import run_worker

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


@router.post("/v1/conversations/{conversation_id}/messages")
async def message(conversation_id: UUID, data: MessageInput, request: Request):
    held = await run_worker(
        owned_unit,
        request,
        turns.prepare,
        conversation_id,
        data,
        request.app.state.settings.processing,
    )
    return StreamingResponse(
        answer_events(request, held),
        media_type="application/x-ndjson",
        headers={"Cache-Control": "private, no-store", "X-Accel-Buffering": "no"},
    )
