import uuid
from datetime import UTC, datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Column,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    String,
    UniqueConstraint,
    Uuid,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB

from app.database.base import Base


def now():
    return datetime.now(UTC)


class AcademicTerm(Base):
    __tablename__ = "academics_term"
    id = Column(Uuid, primary_key=True, default=uuid.uuid4)
    owner_id = Column(Uuid, ForeignKey("archy.accounts_user.id"), nullable=False, index=True)
    name = Column(String(60), nullable=False)
    archived_at = Column(DateTime(timezone=True))
    created_at = Column(DateTime(timezone=True), nullable=False, default=now)
    __table_args__ = (
        UniqueConstraint("owner_id", "id"),
        CheckConstraint("length(btrim(name)) > 0 AND name = btrim(name)", name="name_valid"),
    )


class Timetable(Base):
    __tablename__ = "academics_timetable"
    id = Column(Uuid, primary_key=True, default=uuid.uuid4)
    owner_id = Column(Uuid, nullable=False, index=True)
    term_id = Column(Uuid, nullable=False)
    name = Column(String(60), nullable=False)
    is_primary = Column(Boolean, nullable=False, default=False)
    created_at = Column(DateTime(timezone=True), nullable=False, default=now)
    __table_args__ = (
        UniqueConstraint("owner_id", "id"),
        ForeignKeyConstraint(
            ["owner_id", "term_id"], ["archy.academics_term.owner_id", "archy.academics_term.id"]
        ),
        CheckConstraint("length(btrim(name)) > 0 AND name = btrim(name)", name="name_valid"),
        Index(
            "ix_academics_primary_per_term",
            "term_id",
            unique=True,
            postgresql_where=text("is_primary"),
        ),
    )


class AcademicSelection(Base):
    __tablename__ = "academics_selection"
    owner_id = Column(Uuid, ForeignKey("archy.accounts_user.id"), primary_key=True)
    timetable_id = Column(Uuid, nullable=False)
    __table_args__ = (
        ForeignKeyConstraint(
            ["owner_id", "timetable_id"],
            ["archy.academics_timetable.owner_id", "archy.academics_timetable.id"],
        ),
    )


class CourseSchedule(Base):
    __tablename__ = "academics_schedule"
    id = Column(Uuid, primary_key=True, default=uuid.uuid4)
    course_id = Column(
        Uuid, ForeignKey("archy.courses_course.id", ondelete="CASCADE"), nullable=False, index=True
    )
    position = Column(Integer, nullable=False)
    days = Column(JSONB, nullable=False)
    start_time = Column(String(5), nullable=False)
    end_time = Column(String(5), nullable=False)
    room = Column(String(100), nullable=False, default="")
    __table_args__ = (
        UniqueConstraint("course_id", "position"),
        CheckConstraint(
            "start_time ~ '^([01][0-9]|2[0-3]):[0-5][0-9]$' "
            "AND end_time ~ '^([01][0-9]|2[0-3]):[0-5][0-9]$' AND start_time < end_time",
            name="times_valid",
        ),
        CheckConstraint(
            "jsonb_typeof(days) = 'array' AND jsonb_array_length(days) BETWEEN 1 AND 7",
            name="days_valid",
        ),
    )


class ImportBatch(Base):
    __tablename__ = "academics_import"
    id = Column(Uuid, primary_key=True)
    owner_id = Column(Uuid, ForeignKey("archy.accounts_user.id"), nullable=False, index=True)
    timetable_id = Column(Uuid, nullable=False)
    digest = Column(String(64), nullable=False)
    course_ids = Column(JSONB, nullable=False)
    __table_args__ = (
        ForeignKeyConstraint(
            ["owner_id", "timetable_id"],
            ["archy.academics_timetable.owner_id", "archy.academics_timetable.id"],
        ),
    )
