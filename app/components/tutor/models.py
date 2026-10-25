import uuid

from sqlalchemy import CheckConstraint, Column, DateTime, ForeignKey, Index, String, Text, Uuid
from sqlalchemy.dialects.postgresql import JSONB

from app.components.accounts.models import now
from app.database.base import Base


class Conversation(Base):
    __tablename__ = "tutor_conversation"
    id = Column(Uuid, primary_key=True, default=uuid.uuid4)
    owner_id = Column(Uuid, ForeignKey("archy.accounts_user.id"), nullable=False)
    document_id = Column(Uuid, ForeignKey("archy.documents_document.id"), nullable=False)
    title = Column(String(100), nullable=False)
    created_at = Column(DateTime(timezone=True), nullable=False, default=now)
    __table_args__ = (Index("ix_tutor_conversation_document", "document_id", "created_at"),)


class Message(Base):
    __tablename__ = "tutor_message"
    id = Column(Uuid, primary_key=True, default=uuid.uuid4)
    conversation_id = Column(Uuid, ForeignKey("archy.tutor_conversation.id"), nullable=False)
    role = Column(String(16), nullable=False)
    text = Column(Text, nullable=False)
    sources = Column(JSONB, nullable=False, default=list)
    provider = Column(String(16), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=now)
    __table_args__ = (
        CheckConstraint("role IN ('user','assistant')", name="role_valid"),
        Index("ix_tutor_message_conversation", "conversation_id", "created_at"),
    )
