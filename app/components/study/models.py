from sqlalchemy import CheckConstraint, Column, DateTime, ForeignKey, String, Uuid
from sqlalchemy.dialects.postgresql import JSONB

from app.components.accounts.models import now
from app.database.base import Base


class StudyNote(Base):
    __tablename__ = "study_note"
    document_id = Column(Uuid, ForeignKey("archy.documents_document.id"), primary_key=True)
    source_revision = Column(String(64), nullable=False)
    language = Column(String(2), nullable=False)
    provider = Column(String(16), nullable=False)
    content = Column(JSONB, nullable=False)
    created_at = Column(DateTime(timezone=True), nullable=False, default=now)
    __table_args__ = (CheckConstraint("language IN ('en','ko')", name="language_valid"),)
