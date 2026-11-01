import calendar
from datetime import timedelta

from cryptography.fernet import Fernet
from sqlalchemy import func, select

from app.components.academics.service import lock_owner
from app.components.accounts.models import now
from app.components.billing.models import BillingCustomer, BillingOrder, Subscription
from app.components.courses.models import Course
from app.components.recordings.models import Recording
from app.libs.errors import ApiError
from app.libs.security import digest_token

CATALOG = {
    "plus": {"name": "Archy Plus", "amount": 9900},
    "pro": {"name": "Archy Pro", "amount": 14900},
}
CONSENT = "monthly-test-v1"


def enabled(config):
    if (
        not config.enabled
        or not config.client_key.startswith("test_ck_")
        or not config.secret_key.startswith("test_sk_")
    ):
        raise ApiError(503, "billing_disabled", "Test billing is not configured.")


def month_after(date):
    month = date.month % 12 + 1
    year = date.year + (date.month == 12)
    return date.replace(
        year=year, month=month, day=min(date.day, calendar.monthrange(year, month)[1])
    )


def catalog(settings):
    return {
        "enabled": settings.billing.enabled,
        "mode": "test",
        "currency": "KRW",
        "consent": CONSENT,
        "plans": [
            {"id": "free", "name": "Free", "amount": 0},
            *[{"id": key, **value} for key, value in CATALOG.items()],
        ],
        "maxRecordingSeconds": settings.max_audio_duration_seconds,
    }


def owned(session, owner_id, key):
    row = session.scalar(
        select(BillingOrder).where(BillingOrder.id == key, BillingOrder.owner_id == owner_id)
    )
    if row is None:
        raise ApiError(404)
    return row


def order_response(row):
    return {
        "orderId": row.id,
        "plan": row.plan,
        "amount": row.amount,
        "status": row.status,
        "createdAt": row.created_at.isoformat(),
        "periodEnd": row.period_end.isoformat(),
    }


def checkout(session, settings, owner_id, data):
    enabled(settings.billing)
    lock_owner(session, owner_id)
    existing = session.scalar(
        select(BillingOrder).where(
            BillingOrder.owner_id == owner_id, BillingOrder.request_id == data.requestId
        )
    )
    customer = session.get(BillingCustomer, owner_id)
    if existing:
        if existing.plan != data.plan:
            raise ApiError(409, "order_conflict", "This request already belongs to another plan.")
        row = existing
    else:
        sub = session.get(Subscription, owner_id)
        if sub and sub.period_end > now():
            raise ApiError(409, "active_subscription", "Manage your current subscription first.")
        pending = session.scalar(
            select(BillingOrder).where(
                BillingOrder.owner_id == owner_id,
                BillingOrder.status.in_(["pending", "processing", "review"]),
                BillingOrder.expires_at > now(),
            )
        )
        if pending:
            if (
                pending.plan == data.plan
                and not pending.auth_digest
                and pending.status == "pending"
            ):
                return checkout(
                    session,
                    settings,
                    owner_id,
                    data.model_copy(update={"requestId": pending.request_id}),
                )
            raise ApiError(409, "payment_pending", "Finish or check the pending checkout first.")
        if customer is None:
            customer = BillingCustomer(owner_id=owner_id)
            session.add(customer)
            session.flush()
        row = BillingOrder(
            owner_id=owner_id,
            request_id=data.requestId,
            plan=data.plan,
            amount=CATALOG[data.plan]["amount"],
            period_end=month_after(now()),
            expires_at=now() + timedelta(minutes=30),
        )
        session.add(row)
        session.commit()
    return {
        **order_response(row),
        "requestId": str(row.request_id),
        "clientKey": settings.billing.client_key,
        "customerKey": customer.customer_key,
        "mode": "test",
        "successUrl": settings.frontend_origin + "/billing/success?orderId=" + row.id,
        "failUrl": settings.frontend_origin + "/billing/fail",
    }


def confirm(session, settings, owner_id, data):
    enabled(settings.billing)
    lock_owner(session, owner_id)
    row = owned(session, owner_id, data.orderId)
    customer = session.get(BillingCustomer, owner_id)
    if not customer or customer.customer_key != data.customerKey:
        raise ApiError(400)
    if row.status == "paid":
        return row.id
    if row.status in {"failed", "cancelled", "review"}:
        raise ApiError(409, "payment_pending", "Check this payment in billing settings.")
    digest = digest_token(data.authKey)
    if row.auth_digest and row.auth_digest != digest:
        raise ApiError(409, "order_conflict", "This checkout was already submitted.")
    if not row.auth_digest:
        if row.expires_at <= now():
            raise ApiError(400, "checkout_expired", "Start a new checkout.")
        row.auth_digest = digest
        row.auth_key = (
            Fernet(settings.billing.encryption_key.encode()).encrypt(data.authKey.encode()).decode()
        )
        row.available_at = now()
    session.commit()
    return row.id


def summary(session, owner_id):
    sub = session.get(Subscription, owner_id)
    active = sub is not None and sub.period_end > now()
    start = (
        sub.period_start
        if active
        else now().replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    )
    seconds = session.scalar(
        select(func.coalesce(func.sum(Recording.duration_seconds), 0))
        .join(Course, Recording.course_id == Course.id)
        .where(Course.owner_id == owner_id, Recording.created_at >= start)
    )
    rows = session.scalars(
        select(BillingOrder)
        .where(BillingOrder.owner_id == owner_id)
        .order_by(BillingOrder.created_at.desc())
        .limit(50)
    ).all()
    return {
        "mode": "test",
        "plan": sub.plan if active else "free",
        "usageSeconds": float(seconds),
        "usageSince": start.isoformat(),
        "subscription": {
            "plan": sub.plan,
            "periodEnd": sub.period_end.isoformat(),
            "cancelAtPeriodEnd": sub.cancel_at_period_end,
        }
        if active
        else None,
        "payments": [order_response(row) for row in rows],
    }


def cancel(session, owner_id):
    lock_owner(session, owner_id)
    sub = session.get(Subscription, owner_id)
    if sub:
        sub.cancel_at_period_end = True
    for row in session.scalars(
        select(BillingOrder).where(
            BillingOrder.owner_id == owner_id, BillingOrder.status.in_(["pending", "processing"])
        )
    ):
        row.cancel_renewal = True
    # An in-flight renewal must be reconciled before account closure.
    session.commit()
    return summary(session, owner_id)


def close_allowed(session, owner_id):
    sub = session.get(Subscription, owner_id)
    if sub and not sub.cancel_at_period_end and sub.period_end > now():
        raise ApiError(
            409, "active_subscription", "Cancel your subscription before closing your account."
        )
    pending = session.scalar(
        select(BillingOrder.id).where(
            BillingOrder.owner_id == owner_id,
            BillingOrder.status.in_(["pending", "processing", "review"]),
            BillingOrder.auth_digest.is_not(None),
        )
    )
    if pending:
        raise ApiError(
            409, "payment_pending", "Resolve the pending payment before closing your account."
        )
    if sub:
        sub.cancel_at_period_end = True
    customer = session.get(BillingCustomer, owner_id)
    if customer:
        customer.billing_key = None


def renewal_order(session, owner_id):
    lock_owner(session, owner_id)
    sub = session.get(Subscription, owner_id)
    if not sub or sub.cancel_at_period_end or sub.period_end > now():
        return None
    # The period end is the stable idempotency identity across scheduler runs.
    from uuid import NAMESPACE_URL, uuid5

    key = uuid5(NAMESPACE_URL, f"archy-billing:{owner_id}:{sub.period_end.isoformat()}")
    row = session.scalar(
        select(BillingOrder).where(
            BillingOrder.owner_id == owner_id, BillingOrder.request_id == key
        )
    )
    if row:
        return row.id
    customer = session.get(BillingCustomer, owner_id)
    if not customer or not customer.billing_key:
        return None
    row = BillingOrder(
        owner_id=owner_id,
        request_id=key,
        plan=sub.plan,
        amount=CATALOG[sub.plan]["amount"],
        phase="charge",
        period_start=max(sub.period_end, now()),
        period_end=month_after(max(sub.period_end, now())),
        expires_at=now() + timedelta(hours=12),
        auth_digest="renewal",
    )
    session.add(row)
    session.commit()
    return row.id
