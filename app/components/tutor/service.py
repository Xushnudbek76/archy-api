from datetime import UTC

from sqlalchemy import func, select

from app.components.academics.service import lock_owner
from app.components.documents.service import owned_document
from app.components.tutor.models import Conversation, Message
from app.libs.errors import ApiError


def conversation_response(row):
    return {
        "id": row.id,
        "documentId": row.document_id,
        "title": row.title,
        "createdAt": row.created_at.astimezone(UTC),
    }


def message_response(row):
    return {
        "id": row.id,
        "role": row.role,
        "text": row.text,
        "sources": row.sources,
        "provider": row.provider,
        "createdAt": row.created_at.astimezone(UTC),
    }


def owned_conversation(session, owner_id, conversation_id, *, locked=False):
    if locked:
        lock_owner(session, owner_id)
    query = select(Conversation).where(
        Conversation.id == conversation_id, Conversation.owner_id == owner_id
    )
    if locked:
        query = query.with_for_update()
    row = session.scalar(query)
    if row is None:
        raise ApiError(404)
    owned_document(session, owner_id, row.document_id, writable=locked)
    return row


def create_conversation(session, owner_id, document_id):
    document = owned_document(session, owner_id, document_id, locked=True)
    count = session.scalar(
        select(func.count())
        .select_from(Conversation)
        .where(Conversation.document_id == document_id)
    )
    if count >= 50:
        raise ApiError(
            429, "conversation_limit", "This document has reached its conversation limit."
        )
    row = Conversation(document_id=document_id, owner_id=owner_id, title=document.title)
    session.add(row)
    session.commit()
    return conversation_response(row)


def list_conversations(session, owner_id, document_id):
    owned_document(session, owner_id, document_id)
    rows = session.scalars(
        select(Conversation)
        .where(Conversation.document_id == document_id, Conversation.owner_id == owner_id)
        .order_by(Conversation.created_at.desc(), Conversation.id.desc())
        .limit(50)
    ).all()
    return {"items": [conversation_response(row) for row in rows]}


def read_conversation(session, owner_id, conversation_id):
    row = owned_conversation(session, owner_id, conversation_id)
    messages = session.scalars(
        select(Message)
        .where(Message.conversation_id == row.id)
        .order_by(Message.created_at, Message.id)
        .limit(100)
    ).all()
    return {
        **conversation_response(row),
        "messages": [message_response(message) for message in messages],
    }
