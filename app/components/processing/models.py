import uuid
from datetime import UTC, datetime

from sqlalchemy import (
    CheckConstraint,
    Column,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    Uuid,
)
from sqlalchemy.dialects.postgresql import JSONB

from app.database.base import Base


def now():
    return datetime.now(UTC)


class Job(Base):
    __tablename__ = "processing_job"
    id = Column(Uuid, primary_key=True, default=uuid.uuid4)
    recording_id = Column(
        Uuid,
        ForeignKey("archy.recordings_recording.id", deferrable=True, initially="DEFERRED"),
        nullable=False,
        unique=True,
    )
    stage = Column(String(16), nullable=False, default="QUEUED")
    transcription_attempts = Column(Integer, nullable=False, default=0)
    summary_attempts = Column(Integer, nullable=False, default=0)
    deferrals = Column(Integer, nullable=False, default=0)
    lease_token = Column(Uuid, nullable=True)
    lease_expires_at = Column(DateTime(timezone=True), nullable=True)
    available_at = Column(DateTime(timezone=True), nullable=False, default=now)
    error_code = Column(String(40), nullable=False, default="")
    provider = Column(String(16), nullable=False, default="groq")
    transcription_model = Column(String(80), nullable=False, default="whisper-large-v3-turbo")
    summary_model = Column(String(80), nullable=False, default="openai/gpt-oss-120b")
    prompt_version = Column(String(16), nullable=False, default="lecture-v1")
    configuration = Column(JSONB, nullable=False)
    manifest = Column(JSONB, nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=now)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=now)
    __table_args__ = (
        CheckConstraint(
            "stage IN ('QUEUED','TRANSCRIBING','TRANSCRIBED','SUMMARIZING','COMPLETED','FAILED')",
            name="stage_valid",
        ),
        CheckConstraint(
            "transcription_attempts >= 0 AND summary_attempts >= 0 AND deferrals >= 0",
            name="attempts_valid",
        ),
        CheckConstraint("(lease_token IS NULL) = (lease_expires_at IS NULL)", name="lease_valid"),
        Index("ix_processing_job_claim", "stage", "available_at", "lease_expires_at"),
    )


class TranscriptChunk(Base):
    __tablename__ = "processing_transcript_chunk"
    id = Column(Uuid, primary_key=True, default=uuid.uuid4)
    job_id = Column(Uuid, ForeignKey("archy.processing_job.id", ondelete="CASCADE"), nullable=False)
    sequence = Column(Integer, nullable=False)
    document = Column(JSONB, nullable=False)
    __table_args__ = (UniqueConstraint("job_id", "sequence"),)


class Transcript(Base):
    __tablename__ = "processing_transcript"
    id = Column(Uuid, primary_key=True, default=uuid.uuid4)
    job_id = Column(
        Uuid, ForeignKey("archy.processing_job.id", ondelete="CASCADE"), nullable=False, unique=True
    )
    text = Column(Text, nullable=False)
    segments = Column(JSONB, nullable=False)
    language = Column(String(2), nullable=False)
    provider = Column(String(16), nullable=False)
    model = Column(String(80), nullable=False)
    __table_args__ = (CheckConstraint("language IN ('ko','en')", name="language_valid"),)


class NotePart(Base):
    __tablename__ = "processing_note_part"
    id = Column(Uuid, primary_key=True, default=uuid.uuid4)
    job_id = Column(Uuid, ForeignKey("archy.processing_job.id", ondelete="CASCADE"), nullable=False)
    level = Column(Integer, nullable=False)
    sequence = Column(Integer, nullable=False)
    source_digest = Column(String(64), nullable=False)
    document = Column(JSONB, nullable=False)
    __table_args__ = (UniqueConstraint("job_id", "level", "sequence"),)


class Note(Base):
    __tablename__ = "processing_note"
    id = Column(Uuid, primary_key=True, default=uuid.uuid4)
    job_id = Column(
        Uuid, ForeignKey("archy.processing_job.id", ondelete="CASCADE"), nullable=False, unique=True
    )
    document = Column(JSONB, nullable=False)
    language = Column(String(2), nullable=False)
    provider = Column(String(16), nullable=False)
    model = Column(String(80), nullable=False)
    prompt_version = Column(String(16), nullable=False)
    __table_args__ = (CheckConstraint("language IN ('ko','en')", name="language_valid"),)


class ProviderGate(Base):
    __tablename__ = "processing_provider_gate"
    model = Column(String(80), primary_key=True)
    available_at = Column(DateTime(timezone=True), nullable=False)
