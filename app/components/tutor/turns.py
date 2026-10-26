import hashlib
import json
import re
from datetime import timedelta
from uuid import UUID, uuid4

from sqlalchemy import select, update

from app.components.accounts.models import now
from app.components.documents.service import owned_document
from app.components.documents.sources import document_sources, source_revision
from app.components.tutor import limits
from app.components.tutor.models import Generation, Message
from app.components.tutor.retrieval import build_body, retrieve, terms
from app.components.tutor.service import message_response, owned_conversation
from app.libs.errors import ApiError


def prepare(session, owner_id, conversation_id, data, config):
    conversation = owned_conversation(session, owner_id, conversation_id, locked=True)
    digest = hashlib.sha256(
        json.dumps([data.message, data.language], ensure_ascii=False).encode()
    ).hexdigest()
    generation = session.scalar(
        select(Generation).where(
            Generation.conversation_id == conversation_id,
            Generation.request_id == UUID(data.requestId),
        )
    )
    if generation and generation.payload_digest != digest:
        raise ApiError(409, "request_conflict", "Use a new request ID for a different question.")
    if generation and generation.status == "completed":
        return {"replay": message_response(session.get(Message, generation.assistant_id))}
    active = session.scalar(
        select(Generation.id)
        .where(
            Generation.conversation_id == conversation_id,
            Generation.status == "active",
            Generation.lease_expires_at > now(),
        )
        .limit(1)
    )
    if active:
        raise ApiError(409, "tutor_busy", "An answer is already being generated.", retry_after=5)
    history = session.scalars(
        select(Message)
        .where(Message.conversation_id == conversation_id)
        .order_by(Message.created_at, Message.id)
        .limit(100)
    ).all()
    if len(history) >= 100:
        raise ApiError(
            429, "tutor_history_limit", "Start a new conversation to ask more questions."
        )
    items = document_sources(session, owner_id, conversation.document_id)
    query = data.message
    if not terms(query):
        query += " " + next((item.text for item in reversed(history) if item.role == "user"), "")
    sources = retrieve(items, query)
    if sources and (
        config.backend == "disabled" or (config.backend == "groq" and not config.api_key)
    ):
        raise ApiError(
            503, "tutor_unavailable", "Configure the tutor AI provider before asking questions."
        )
    body = build_body(
        sources, [message_response(item) for item in history], data.message, data.language
    )
    limits.reserve(session, owner_id, config.backend, has_sources=bool(sources))
    if generation is None:
        generation = Generation(
            conversation_id=conversation_id, request_id=UUID(data.requestId), payload_digest=digest
        )
        session.add(generation)
    generation.status = "active"
    generation.lease_token = uuid4()
    generation.lease_expires_at = now() + timedelta(seconds=64)
    session.commit()
    return {
        "generationId": generation.id,
        "token": generation.lease_token,
        "conversationId": conversation_id,
        "documentId": conversation.document_id,
        "message": data.message,
        "language": data.language,
        "sources": sources,
        "revision": source_revision(items),
        "body": body,
        "config": config,
    }


def validate_answer(text, sources):
    known = {source["id"] for source in sources}
    references = set(re.findall(r"(?:pdf|transcript):[A-Za-z0-9_-]+", text))
    if not text.strip() or len(text.encode()) > 12000 or not references <= known:
        raise ApiError(
            502, "invalid_provider_output", "The tutor returned an invalid answer. Try again."
        )


def finish(session, owner_id, held, text, provider):
    conversation = owned_conversation(session, owner_id, held["conversationId"], locked=True)
    owned_document(session, owner_id, conversation.document_id, locked=True)
    generation = session.scalar(
        select(Generation).where(Generation.id == held["generationId"]).with_for_update()
    )
    if (
        generation.status != "active"
        or generation.lease_token != held["token"]
        or generation.lease_expires_at <= now()
    ):
        raise ApiError(409, "tutor_lease_lost", "The answer expired. Retry the question.")
    items = document_sources(session, owner_id, conversation.document_id)
    if source_revision(items) != held["revision"]:
        raise ApiError(409, "source_changed", "The document changed. Retry your question.")
    by_id = {item["id"]: item for item in items}
    for item in held["sources"]:
        original = by_id.get(item["id"])
        if (
            original is None
            or item["text"] not in original["text"]
            or any(item[key] != original[key] for key in ("kind", "page", "start", "end"))
        ):
            raise ApiError(502, "invalid_provider_output")
    validate_answer(text, held["sources"])
    timestamp = now()
    user = Message(
        conversation_id=conversation.id,
        role="user",
        text=held["message"],
        sources=[],
        provider=None,
        created_at=timestamp,
    )
    assistant = Message(
        conversation_id=conversation.id,
        role="assistant",
        text=text,
        sources=held["sources"],
        provider=provider,
        created_at=timestamp + timedelta(microseconds=1),
    )
    session.add_all([user, assistant])
    session.flush()
    generation.status, generation.assistant_id = "completed", assistant.id
    generation.lease_token = generation.lease_expires_at = None
    session.commit()
    return str(assistant.id)


def release(session, held):
    session.execute(
        update(Generation)
        .where(
            Generation.id == held["generationId"],
            Generation.lease_token == held["token"],
            Generation.status == "active",
        )
        .values(status="failed", lease_token=None, lease_expires_at=None)
    )
    session.commit()
