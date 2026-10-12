import uuid
from datetime import UTC, datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Column,
    DateTime,
    ForeignKeyConstraint,
    Index,
    PrimaryKeyConstraint,
    String,
    UniqueConstraint,
    Uuid,
    text,
)

from app.database.base import Base


def now():
    return datetime.now(UTC)


class User(Base):
    __tablename__ = "accounts_user"
    password = Column(String(128), nullable=False)
    last_login = Column(DateTime(timezone=True), nullable=True)
    is_superuser = Column(Boolean, nullable=False, default=False)
    id = Column(Uuid, nullable=False, default=uuid.uuid4)
    email = Column(String(254), nullable=False)
    display_name = Column(String(100), nullable=False, default="")
    is_active = Column(Boolean, nullable=False, default=False)
    is_staff = Column(Boolean, nullable=False, default=False)
    created_at = Column(DateTime(timezone=True), nullable=False, default=now)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=now)
    email_confirmed_at = Column(DateTime(timezone=True), nullable=True)
    __table_args__ = (
        UniqueConstraint("email", name="accounts_user_email_key"),
        PrimaryKeyConstraint("id", name="accounts_user_pkey"),
        Index(
            "accounts_user_email_b2644a56_like",
            "email",
            postgresql_ops={"email": "varchar_pattern_ops"},
        ),
        Index("user_email_case_unique", text("lower(email::text)"), unique=True),
    )


class SignupAttempt(Base):
    __tablename__ = "accounts_signupattempt"
    id = Column(Uuid, nullable=False, default=uuid.uuid4)
    password_hash = Column(String(128), nullable=False)
    display_name = Column(String(100), nullable=False, default="")
    created_at = Column(DateTime(timezone=True), nullable=False, default=now)
    user_id = Column(Uuid, nullable=False)
    __table_args__ = (
        PrimaryKeyConstraint("id", name="accounts_signupattempt_pkey"),
        ForeignKeyConstraint(
            ["user_id"],
            ["archy.accounts_user.id"],
            name="accounts_signupattempt_user_id_58cd6f0b_fk_accounts_user_id",
            deferrable=True,
            initially="DEFERRED",
        ),
        Index("accounts_signupattempt_user_id_58cd6f0b", "user_id"),
    )


class AccountSession(Base):
    __tablename__ = "accounts_session"
    id = Column(Uuid, primary_key=True, default=uuid.uuid4)
    user_id = Column(Uuid, nullable=False)
    digest = Column(String(64), nullable=False, unique=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=now)
    expires_at = Column(DateTime(timezone=True), nullable=False)
    __table_args__ = (
        ForeignKeyConstraint(["user_id"], ["archy.accounts_user.id"], ondelete="CASCADE"),
        Index("ix_accounts_session_user_id", "user_id"),
        Index("ix_accounts_session_expires_at", "expires_at"),
    )


class ActionToken(Base):
    __tablename__ = "accounts_actiontoken"
    id = Column(Uuid, primary_key=True, default=uuid.uuid4)
    user_id = Column(Uuid, nullable=False)
    signup_attempt_id = Column(Uuid, nullable=True)
    digest = Column(String(64), nullable=False, unique=True)
    purpose = Column(String(16), nullable=False)
    created_at = Column(DateTime(timezone=True), nullable=False, default=now)
    expires_at = Column(DateTime(timezone=True), nullable=False)
    consumed_at = Column(DateTime(timezone=True), nullable=True)
    __table_args__ = (
        ForeignKeyConstraint(["user_id"], ["archy.accounts_user.id"], ondelete="CASCADE"),
        ForeignKeyConstraint(
            ["signup_attempt_id"], ["archy.accounts_signupattempt.id"], ondelete="SET NULL"
        ),
        Index("ix_accounts_actiontoken_user_id", "user_id"),
        CheckConstraint("purpose IN ('confirm', 'reset')", name="purpose_valid"),
    )
