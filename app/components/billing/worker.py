from dataclasses import dataclass
from datetime import datetime, timedelta
from uuid import uuid4

from cryptography.fernet import Fernet, InvalidToken
from sqlalchemy import or_, select

from app.components.academics.service import lock_owner
from app.components.accounts.models import User, now
from app.components.billing import provider
from app.components.billing.models import BillingCustomer, BillingOrder, Subscription
from app.components.billing.service import CATALOG, enabled, month_after
from app.libs.errors import ApiError


@dataclass(frozen=True)
class Work:
    order_id: str
    owner_id: object
    lease: object
    phase: str
    customer_key: str
    secret: str
    amount: int
    plan: str


def claim(sessions, config, key):
    with sessions() as session:
        row = session.get(BillingOrder, key)
        if row is None:
            return None
        lock_owner(session, row.owner_id)
        row = session.scalar(select(BillingOrder).where(BillingOrder.id == key).with_for_update())
        if (
            row.status not in {"pending", "processing"}
            or not row.auth_digest
            or row.available_at > now()
            or (row.lease_until and row.lease_until > now())
        ):
            return None
        if row.attempts >= 8 or row.created_at < now() - timedelta(hours=12):
            row.status = "review"
            session.commit()
            return None
        sub = session.get(Subscription, row.owner_id)
        if row.auth_digest == "renewal" and sub and sub.cancel_at_period_end:
            row.status = "cancelled"
            session.commit()
            return None
        customer = session.get(BillingCustomer, row.owner_id)
        encrypted = row.auth_key if row.phase == "issue" else customer.billing_key
        if not encrypted:
            row.status = "review"
            session.commit()
            return None
        try:
            secret = Fernet(config.encryption_key.encode()).decrypt(encrypted.encode()).decode()
        except InvalidToken:
            row.status = "review"
            session.commit()
            return None
        row.lease = uuid4()
        row.lease_until = now() + timedelta(minutes=3)
        row.status = "processing"
        row.attempts += 1
        work = Work(
            row.id,
            row.owner_id,
            row.lease,
            row.phase,
            customer.customer_key,
            secret,
            row.amount,
            row.plan,
        )
        session.commit()
        return work


def locked(session, work):
    lock_owner(session, work.owner_id)
    row = session.scalar(
        select(BillingOrder).where(BillingOrder.id == work.order_id).with_for_update()
    )
    return row if row and row.lease == work.lease and row.status == "processing" else None


def save_key(sessions, config, work, value):
    with sessions() as session:
        row = locked(session, work)
        if row is None:
            return False
        key = value.get("billingKey") if isinstance(value, dict) else None
        if (
            not isinstance(key, str)
            or not 1 <= len(key) <= 200
            or value.get("customerKey") != work.customer_key
        ):
            row.status = "review"
            row.auth_key = None
            session.commit()
            return False
        session.get(BillingCustomer, work.owner_id).billing_key = (
            Fernet(config.encryption_key.encode()).encrypt(key.encode()).decode()
        )
        row.auth_key = None
        row.phase = "charge"
        row.lease = row.lease_until = None
        row.available_at = now()
        session.commit()
        return True


def apply_payment(session, row, value):
    if (
        not isinstance(value, dict)
        or value.get("orderId") != row.id
        or type(value.get("totalAmount")) is not int
        or value["totalAmount"] != row.amount
        or value.get("currency") != "KRW"
        or not isinstance(value.get("paymentKey"), str)
        or not 1 <= len(value["paymentKey"]) <= 200
    ):
        row.status = "review"
        return
    if row.payment_key and row.payment_key != value["paymentKey"]:
        row.status = "review"
        return
    sub = session.get(Subscription, row.owner_id)
    status = value.get("status")
    if status == "CANCELED":
        row.status = "cancelled"
        if sub and sub.latest_order == row.id:
            sub.period_end = now()
            sub.cancel_at_period_end = True
        return
    if status != "DONE":
        if status in {"ABORTED", "EXPIRED"}:
            row.status = "failed"
        elif status == "PARTIAL_CANCELED":
            row.status = "review"
        return
    # A delayed old approval cannot undo an already verified cancellation.
    if row.status == "cancelled":
        return
    try:
        approved = datetime.fromisoformat(value["approvedAt"].replace("Z", "+00:00"))
        if approved.tzinfo is None or approved > now() + timedelta(minutes=5):
            raise ValueError
    except (KeyError, TypeError, ValueError, AttributeError):
        row.status = "review"
        return
    if row.status == "paid":
        return
    row.payment_key = value["paymentKey"]
    row.approved_at = approved
    row.status = "paid"
    row.auth_key = None
    if row.auth_digest != "renewal":
        row.period_start = approved
        row.period_end = month_after(approved)
    if not sub:
        session.add(
            Subscription(
                owner_id=row.owner_id,
                plan=row.plan,
                period_start=row.period_start,
                period_end=row.period_end,
                latest_order=row.id,
                cancel_at_period_end=row.cancel_renewal,
            )
        )
    elif sub.period_start <= row.period_start:
        sub.plan = row.plan
        sub.period_start = row.period_start
        sub.period_end = row.period_end
        sub.latest_order = row.id
        if row.auth_digest != "renewal":
            sub.cancel_at_period_end = row.cancel_renewal


def process(sessions, config, key):
    enabled(config)
    for _ in range(2):
        work = claim(sessions, config, key)
        if work is None:
            return
        try:
            if work.phase == "issue":
                value = provider.request(
                    config,
                    "POST",
                    "/billing/authorizations/issue",
                    {"authKey": work.secret, "customerKey": work.customer_key},
                    key="issue-" + work.order_id,
                )
                if save_key(sessions, config, work, value):
                    continue
                return
            value = provider.request(config, "GET", provider.order_path(work.order_id))
            if value is None:
                value = provider.request(
                    config,
                    "POST",
                    provider.billing_path(work.secret),
                    {
                        "customerKey": work.customer_key,
                        "amount": work.amount,
                        "orderId": work.order_id,
                        "orderName": CATALOG[work.plan]["name"] + " monthly (test)",
                    },
                    key="charge-" + work.order_id,
                )
            with sessions() as session:
                row = locked(session, work)
                if row is not None:
                    apply_payment(session, row, value)
                    row.lease = row.lease_until = None
                    if row.status == "processing":
                        row.available_at = now() + timedelta(minutes=2)
                    session.commit()
            return
        except ApiError:
            with sessions() as session:
                row = locked(session, work)
                if row:
                    row.lease = row.lease_until = None
                    row.available_at = now() + timedelta(seconds=min(3600, 60 * 2**row.attempts))
                    session.commit()
            return


def reconcile(sessions, config, key):
    enabled(config)
    with sessions() as session:
        row = session.get(BillingOrder, key)
        if not row:
            return
        owner = row.owner_id
    value = provider.request(config, "GET", provider.order_path(key))
    if value is None:
        return
    with sessions() as session:
        lock_owner(session, owner)
        row = session.scalar(select(BillingOrder).where(BillingOrder.id == key).with_for_update())
        apply_payment(session, row, value)
        session.commit()


def run_due(sessions, config, limit=20):
    enabled(config)
    from app.components.billing.service import renewal_order

    with sessions() as session:
        owners = session.scalars(
            select(Subscription.owner_id)
            .join(User, User.id == Subscription.owner_id)
            .where(
                Subscription.cancel_at_period_end.is_(False),
                Subscription.period_end <= now(),
                User.is_active.is_(True),
            )
            .limit(limit)
        ).all()
    for owner in owners:
        with sessions() as session:
            key = renewal_order(session, owner)
        if key:
            process(sessions, config, key)
    with sessions() as session:
        keys = session.scalars(
            select(BillingOrder.id)
            .join(User, User.id == BillingOrder.owner_id)
            .where(
                User.is_active.is_(True),
                BillingOrder.status.in_(["pending", "processing"]),
                BillingOrder.auth_digest.is_not(None),
                BillingOrder.available_at <= now(),
                or_(BillingOrder.lease_until.is_(None), BillingOrder.lease_until < now()),
            )
            .order_by(BillingOrder.available_at)
            .limit(limit)
        ).all()
    for key in keys:
        process(sessions, config, key)
