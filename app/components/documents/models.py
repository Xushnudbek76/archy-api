import uuid

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    Column,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    Uuid,
)

from app.components.accounts.models import now
from app.database.base import Base


class Document(Base):
    __tablename__ = "documents_document"
    id = Column(Uuid, primary_key=True, default=uuid.uuid4)
    owner_id = Column(Uuid, ForeignKey("archy.accounts_user.id"), nullable=False)
    title = Column(String(100), nullable=False)
    course_id = Column(Uuid, ForeignKey("archy.courses_course.id"), nullable=True)
    recording_id = Column(Uuid, ForeignKey("archy.recordings_recording.id"), nullable=True)
    file_name = Column(String(255), nullable=True)
    pdf_size_bytes = Column(BigInteger, nullable=True)
    page_count = Column(Integer, nullable=True)
    text = Column(Text, nullable=True)
    archived_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=now)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=now)
    __table_args__ = (
        CheckConstraint(
            "length(trim(title)) > 0 AND length(title) <= 100 AND title = trim(title)",
            name="title_valid",
        ),
        CheckConstraint(
            "(file_name IS NULL) = (pdf_size_bytes IS NULL)", name="pdf_metadata_valid"
        ),
        CheckConstraint(
            "pdf_size_bytes IS NULL OR pdf_size_bytes BETWEEN 1 AND 20971520", name="pdf_size_valid"
        ),
        CheckConstraint(
            "page_count IS NULL OR page_count BETWEEN 1 AND 200", name="page_count_valid"
        ),
        CheckConstraint("text IS NULL OR length(text) <= 500000", name="text_size_valid"),
        Index("ix_documents_owner_created", "owner_id", "created_at", "id"),
    )
