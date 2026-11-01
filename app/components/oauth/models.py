from uuid import uuid4

from sqlalchemy import Column, DateTime, ForeignKey, Index, String, UniqueConstraint, Uuid

from app.components.accounts.models import now
from app.database.base import Base


class OAuthIdentity(Base):
    __tablename__ = "oauth_identity"
    id = Column(Uuid, primary_key=True, default=uuid4)
    owner_id = Column(
        Uuid, ForeignKey("archy.accounts_user.id", ondelete="CASCADE"), nullable=False
    )
    provider = Column(String(10), nullable=False)
    subject = Column(String(255), nullable=False)
    created_at = Column(DateTime(timezone=True), nullable=False, default=now)
    __table_args__ = (
        UniqueConstraint("provider", "subject"),
        Index("ix_oauth_identity_owner", "owner_id"),
    )


class OAuthState(Base):
    __tablename__ = "oauth_state"
    digest = Column(String(64), primary_key=True)
    browser_digest = Column(String(64), nullable=False)
    provider = Column(String(10), nullable=False)
    nonce = Column(String(64), nullable=False)
    verifier = Column(String(128), nullable=False)
    return_to = Column(String(100), nullable=False)
    expires_at = Column(DateTime(timezone=True), nullable=False)
    consumed_at = Column(DateTime(timezone=True))
    __table_args__ = (Index("ix_oauth_state_expiry", "expires_at"),)
