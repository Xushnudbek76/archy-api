from uuid import uuid4

from sqlalchemy import (
    Boolean,
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

from app.components.accounts.models import now
from app.database.base import Base


class BillingCustomer(Base):
    __tablename__ = "billing_customer"
    owner_id = Column(Uuid, ForeignKey("archy.accounts_user.id"), primary_key=True)
    customer_key = Column(String(50), nullable=False, unique=True, default=lambda: str(uuid4()))
    billing_key = Column(Text)


class Subscription(Base):
    __tablename__ = "billing_subscription"
    owner_id = Column(Uuid, ForeignKey("archy.accounts_user.id"), primary_key=True)
    plan = Column(String(10), nullable=False)
    period_start = Column(DateTime(timezone=True), nullable=False)
    period_end = Column(DateTime(timezone=True), nullable=False)
    cancel_at_period_end = Column(Boolean, nullable=False, default=False)
    latest_order = Column(String(50), nullable=False)
    __table_args__ = (Index("ix_billing_subscription_due", "period_end"),)


class BillingOrder(Base):
    __tablename__ = "billing_order"
    id = Column(String(50), primary_key=True, default=lambda: "archy_" + uuid4().hex)
    owner_id = Column(Uuid, ForeignKey("archy.accounts_user.id"), nullable=False)
    request_id = Column(Uuid, nullable=False)
    plan = Column(String(10), nullable=False)
    amount = Column(Integer, nullable=False)
    status = Column(String(12), nullable=False, default="pending")
    phase = Column(String(12), nullable=False, default="issue")
    auth_digest = Column(String(64))
    auth_key = Column(Text)
    payment_key = Column(String(200), unique=True)
    approved_at = Column(DateTime(timezone=True))
    period_start = Column(DateTime(timezone=True), nullable=False, default=now)
    period_end = Column(DateTime(timezone=True), nullable=False)
    created_at = Column(DateTime(timezone=True), nullable=False, default=now)
    expires_at = Column(DateTime(timezone=True), nullable=False)
    available_at = Column(DateTime(timezone=True), nullable=False, default=now)
    lease = Column(Uuid)
    lease_until = Column(DateTime(timezone=True))
    attempts = Column(Integer, nullable=False, default=0)
    cancel_renewal = Column(Boolean, nullable=False, default=False, server_default="false")
    __table_args__ = (
        UniqueConstraint("owner_id", "request_id"),
        CheckConstraint(
            "status IN ('pending','processing','paid','failed','review','cancelled')",
            name="status_valid",
        ),
        CheckConstraint("amount > 0 AND attempts BETWEEN 0 AND 8", name="bounds_valid"),
        Index("ix_billing_order_owner", "owner_id", "created_at"),
        Index("ix_billing_order_due", "available_at"),
    )
