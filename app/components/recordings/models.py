import uuid
from datetime import UTC, datetime

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    Column,
    DateTime,
    Double,
    ForeignKeyConstraint,
    Index,
    Integer,
    PrimaryKeyConstraint,
    String,
    UniqueConstraint,
    Uuid,
    text,
)
from sqlalchemy.schema import conv

from app.database.base import Base


def now():
    return datetime.now(UTC)


class Upload(Base):
    __tablename__ = "recordings_upload"
    id = Column(Uuid, nullable=False, default=uuid.uuid4)
    title = Column(String(100), nullable=False)
    file_name = Column(String(255), nullable=False)
    size_bytes = Column(BigInteger, nullable=False)
    uploaded_bytes = Column(BigInteger, nullable=False, default=0)
    sha256 = Column(String(64), nullable=False)
    status = Column(String(12), nullable=False, default="UPLOADING")
    error_code = Column(String(32), nullable=False, default="")
    created_at = Column(DateTime(timezone=True), nullable=False, default=now)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=now)
    course_id = Column(Uuid, nullable=False)
    max_duration_seconds = Column(Integer, nullable=True)
    __table_args__ = (
        ForeignKeyConstraint(
            ["course_id"],
            ["archy.courses_course.id"],
            name="recordings_upload_course_id_13a40453_fk_courses_course_id",
            deferrable=True,
            initially="DEFERRED",
        ),
        PrimaryKeyConstraint("id", name="recordings_upload_pkey"),
        CheckConstraint(
            "max_duration_seconds IS NULL OR max_duration_seconds > 0",
            name=conv("upload_duration_policy_valid"),
        ),
        CheckConstraint("((size_bytes >= 0))", name=conv("recordings_upload_size_bytes_check")),
        CheckConstraint(
            "((uploaded_bytes >= 0))", name=conv("recordings_upload_uploaded_bytes_check")
        ),
        CheckConstraint("((uploaded_bytes <= size_bytes))", name=conv("upload_offset_valid")),
        CheckConstraint(
            "(((size_bytes > 0) AND (size_bytes <= '9007199254740991'::bigint)))",
            name=conv("upload_size_valid"),
        ),
        CheckConstraint(
            (
                "(((status)::text = ANY ((ARRAY['UPLOADING'::character varying, "
                "'ACCEPTED'::character varying, 'FAILED'::character varying, "
                "'CANCELLED'::character varying])::text[])))"
            ),
            name=conv("upload_status_valid"),
        ),
        CheckConstraint(
            (
                "(((length(TRIM(BOTH FROM title)) > 0) AND (length((title)::text) <= 100) "
                "AND ((title)::text = TRIM(BOTH FROM title))))"
            ),
            name=conv("upload_title_valid"),
        ),
        Index("recordings__course__619b85_idx", "course_id", "status", text("created_at DESC")),
        Index("recordings_upload_course_id_13a40453", "course_id"),
    )


class Recording(Base):
    __tablename__ = "recordings_recording"
    id = Column(Uuid, nullable=False, default=uuid.uuid4)
    title = Column(String(100), nullable=False)
    size_bytes = Column(BigInteger, nullable=False)
    sha256 = Column(String(64), nullable=False)
    content_type = Column(String(32), nullable=False)
    duration_seconds = Column(Double, nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=now)
    course_id = Column(Uuid, nullable=False)
    upload_id = Column(Uuid, nullable=False)
    __table_args__ = (
        ForeignKeyConstraint(
            ["course_id"],
            ["archy.courses_course.id"],
            name="recordings_recording_course_id_e8867e2e_fk_courses_course_id",
            deferrable=True,
            initially="DEFERRED",
        ),
        PrimaryKeyConstraint("id", name="recordings_recording_pkey"),
        CheckConstraint("((size_bytes >= 0))", name=conv("recordings_recording_size_bytes_check")),
        ForeignKeyConstraint(
            ["upload_id"],
            ["archy.recordings_upload.id"],
            name="recordings_recording_upload_id_6cab6225_fk_recordings_upload_id",
            deferrable=True,
            initially="DEFERRED",
        ),
        UniqueConstraint("upload_id", name="recordings_recording_upload_id_key"),
        Index("recordings__course__41d681_idx", "course_id", text("created_at DESC")),
        Index("recordings_recording_course_id_e8867e2e", "course_id"),
    )
