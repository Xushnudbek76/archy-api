import uuid

from sqlalchemy import CheckConstraint, Column, DateTime, ForeignKey, Integer, String, Text, Uuid
from sqlalchemy.dialects.postgresql import JSONB

from app.components.accounts.models import now
from app.database.base import Base


class Profile(Base):
    __tablename__ = "preferences_profile"
    owner_id = Column(Uuid, ForeignKey("archy.accounts_user.id"), primary_key=True)
    university = Column(String(100), nullable=False, default="", server_default="")
    department = Column(String(100), nullable=False, default="", server_default="")
    ui_language = Column(String(2), nullable=False, default="en", server_default="en")
    summary_language = Column(String(4), nullable=False, default="auto", server_default="auto")
    note_format = Column(String(36), nullable=False, default="outline", server_default="outline")
    updated_at = Column(DateTime(timezone=True), nullable=False, default=now)
    __table_args__ = (
        CheckConstraint("ui_language IN ('en','ko')", name="ui_language_valid"),
        CheckConstraint("summary_language IN ('auto','en','ko')", name="summary_language_valid"),
    )


class NoteFormat(Base):
    __tablename__ = "preferences_format"
    id = Column(Uuid, primary_key=True, default=uuid.uuid4)
    owner_id = Column(Uuid, ForeignKey("archy.accounts_user.id"), nullable=False, index=True)
    name = Column(String(60), nullable=False)
    instructions = Column(Text, nullable=False)
    created_at = Column(DateTime(timezone=True), nullable=False, default=now)
    __table_args__ = (
        CheckConstraint(
            "length(btrim(name)) BETWEEN 1 AND 60 AND name = btrim(name)", name="name_valid"
        ),
        CheckConstraint("length(btrim(instructions)) BETWEEN 1 AND 300", name="instructions_valid"),
    )


class MediaPurge(Base):
    __tablename__ = "preferences_media_purge"
    id = Column(Uuid, primary_key=True, default=uuid.uuid4)
    owner_id = Column(Uuid, ForeignKey("archy.accounts_user.id"), nullable=False)
    media = Column(JSONB, nullable=False)
    attempts = Column(Integer, nullable=False, default=0)
    available_at = Column(DateTime(timezone=True), nullable=False, default=now)
    created_at = Column(DateTime(timezone=True), nullable=False, default=now)
    __table_args__ = (CheckConstraint("attempts BETWEEN 0 AND 8", name="attempts_valid"),)
