import uuid
from datetime import UTC, datetime

from sqlalchemy import (
    CheckConstraint,
    Column,
    DateTime,
    ForeignKeyConstraint,
    Index,
    PrimaryKeyConstraint,
    String,
    Uuid,
)
from sqlalchemy.schema import conv

from app.database.base import Base


def now():
    return datetime.now(UTC)


class Course(Base):
    __tablename__ = "courses_course"
    id = Column(Uuid, nullable=False, default=uuid.uuid4)
    title = Column(String(100), nullable=False)
    archived_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=now)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=now)
    owner_id = Column(Uuid, nullable=False)
    __table_args__ = (
        CheckConstraint(
            (
                "(((length(TRIM(BOTH FROM title)) > 0) AND (length((title)::text) <= 100) "
                "AND ((title)::text = TRIM(BOTH FROM title))))"
            ),
            name=conv("course_title_valid"),
        ),
        ForeignKeyConstraint(
            ["owner_id"],
            ["archy.accounts_user.id"],
            name="courses_course_owner_id_97a468c6_fk_accounts_user_id",
            deferrable=True,
            initially="DEFERRED",
        ),
        PrimaryKeyConstraint("id", name="courses_course_pkey"),
        Index("courses_course_owner_id_97a468c6", "owner_id"),
    )
