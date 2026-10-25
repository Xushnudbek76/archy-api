import uuid

from sqlalchemy import (
    CheckConstraint,
    Column,
    DateTime,
    ForeignKey,
    Integer,
    String,
    UniqueConstraint,
    Uuid,
)
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


class Quiz(Base):
    __tablename__ = "study_quiz"
    id = Column(Uuid, primary_key=True, default=uuid.uuid4)
    document_id = Column(Uuid, ForeignKey("archy.documents_document.id"), nullable=False)
    title = Column(String(100), nullable=False)
    source_revision = Column(String(64), nullable=False)
    language = Column(String(2), nullable=False)
    provider = Column(String(16), nullable=False)
    questions = Column(JSONB, nullable=False)
    created_at = Column(DateTime(timezone=True), nullable=False, default=now)
    __table_args__ = (CheckConstraint("language IN ('en','ko')", name="language_valid"),)


class Attempt(Base):
    __tablename__ = "study_attempt"
    id = Column(Uuid, primary_key=True, default=uuid.uuid4)
    quiz_id = Column(Uuid, ForeignKey("archy.study_quiz.id"), nullable=False)
    answer_digest = Column(String(64), nullable=False)
    score = Column(Integer, nullable=False)
    total = Column(Integer, nullable=False)
    results = Column(JSONB, nullable=False)
    created_at = Column(DateTime(timezone=True), nullable=False, default=now)
    __table_args__ = (
        UniqueConstraint("quiz_id", "answer_digest"),
        CheckConstraint(
            "score >= 0 AND score <= total AND total BETWEEN 1 AND 15", name="score_valid"
        ),
    )
