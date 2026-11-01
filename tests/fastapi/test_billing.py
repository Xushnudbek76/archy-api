from dataclasses import replace
from datetime import UTC, datetime, timedelta

from cryptography.fernet import Fernet
from sqlalchemy import select

from app.components.billing.config import BillingSettings
from app.components.billing.models import BillingOrder, Subscription
from tests.fastapi.test_accounts import post
from tests.fastapi.test_courses import signin


def configure(client):
    client.app.state.settings = replace(
        client.app.state.settings,
        billing=BillingSettings(
            "test_ck_fixture", "test_sk_fixture", Fernet.generate_key().decode()
        ),
    )


def checkout(client):
    from uuid import uuid4

    response = post(
        client,
        "/v1/billing/checkout",
        {"plan": "plus", "requestId": str(uuid4()), "consent": "monthly-test-v1"},
    )
    assert response.status_code == 201
    return response.json()


def payment(order_id, amount=9900, status="DONE"):
    return {
        "orderId": order_id,
        "paymentKey": "fixture-payment",
        "status": status,
        "totalAmount": amount,
        "currency": "KRW",
        "approvedAt": datetime.now(UTC).isoformat(),
    }


def test_billing_catalog_is_test_only_and_checkout_is_server_owned(api_client):
    client = api_client
    assert client.get("/v1/billing/catalog").json()["enabled"] is False
    signin(client)
    assert (
        post(
            client,
            "/v1/billing/checkout",
            {"plan": "plus", "requestId": "bad", "consent": "monthly-test-v1"},
        ).status_code
        == 400
    )
    configure(client)
    order = checkout(client)
    assert order["amount"] == 9900 and order["mode"] == "test"
    repeated = post(
        client,
        "/v1/billing/checkout",
        {"plan": "plus", "requestId": order["requestId"], "consent": "monthly-test-v1"},
    )
    assert repeated.json()["orderId"] == order["orderId"]
    assert (
        post(
            client,
            "/v1/billing/checkout",
            {
                "plan": "plus",
                "requestId": order["requestId"],
                "consent": "monthly-test-v1",
                "amount": 1,
            },
        ).status_code
        == 400
    )


def test_billing_confirmation_is_verified_idempotent_and_cancel_stops_renewal(
    api_client, monkeypatch
):
    client = api_client
    signin(client)
    configure(client)
    order = checkout(client)
    calls = []

    def request(config, method, path, body=None, key=None):
        calls.append((method, path, key))
        if path.endswith("/issue"):
            return {"customerKey": order["customerKey"], "billingKey": "fixture-billing-key"}
        if method == "GET":
            return None
        return payment(order["orderId"])

    monkeypatch.setattr("app.components.billing.provider.request", request)
    data = {
        "orderId": order["orderId"],
        "customerKey": order["customerKey"],
        "authKey": "fixture-auth",
    }
    assert post(client, "/v1/billing/confirm", data).json()["status"] == "paid"
    assert post(client, "/v1/billing/confirm", data).json()["status"] == "paid"
    assert (
        len([call for call in calls if call[0] == "POST" and not call[1].endswith("/issue")]) == 1
    )
    summary = client.get("/v1/billing").json()
    assert summary["plan"] == "plus" and summary["subscription"]["cancelAtPeriodEnd"] is False
    assert post(client, "/v1/billing/cancel", {}).status_code == 200
    assert post(client, "/v1/billing/cancel", {}).status_code == 200
    assert client.get("/v1/billing").json()["subscription"]["cancelAtPeriodEnd"] is True
    with client.app.state.sessions() as session:
        sub = session.scalar(select(Subscription))
        sub.period_end = datetime.now(UTC) - timedelta(seconds=1)
        session.commit()
    assert client.get("/v1/billing").json()["plan"] == "free"
    with client.app.state.sessions() as session:
        assert session.scalar(select(BillingOrder)).payment_key == "fixture-payment"


def test_mismatched_provider_amount_never_creates_entitlement(api_client, monkeypatch):
    client = api_client
    signin(client)
    configure(client)
    order = checkout(client)

    def request(config, method, path, body=None, key=None):
        if path.endswith("/issue"):
            return {"customerKey": order["customerKey"], "billingKey": "fixture-billing-key"}
        if method == "GET":
            return None
        return payment(order["orderId"], 1)

    monkeypatch.setattr("app.components.billing.provider.request", request)
    assert (
        post(
            client,
            "/v1/billing/confirm",
            {
                "orderId": order["orderId"],
                "customerKey": order["customerKey"],
                "authKey": "fixture-auth",
            },
        ).json()["status"]
        == "review"
    )
    assert client.get("/v1/billing").json()["plan"] == "free"


def test_lost_provider_response_resumes_without_repeating_a_charge(api_client, monkeypatch):
    from app.components.accounts.models import now
    from app.components.billing.worker import process
    from app.libs.errors import ApiError

    client = api_client
    signin(client)
    configure(client)
    order = checkout(client)
    charged = []

    def request(config, method, path, body=None, key=None):
        if path.endswith("/issue"):
            return {"customerKey": order["customerKey"], "billingKey": "fixture-billing-key"}
        if method == "GET":
            return payment(order["orderId"]) if charged else None
        charged.append(key)
        raise ApiError(503)

    monkeypatch.setattr("app.components.billing.provider.request", request)
    data = {
        "orderId": order["orderId"],
        "customerKey": order["customerKey"],
        "authKey": "fixture-auth",
    }
    assert post(client, "/v1/billing/confirm", data).json()["status"] == "processing"
    assert client.get("/v1/billing").json()["plan"] == "free"
    with client.app.state.sessions() as session:
        row = session.get(BillingOrder, order["orderId"])
        row.available_at = now()
        session.commit()
    process(client.app.state.sessions, client.app.state.settings.billing, order["orderId"])
    assert len(charged) == 1
    assert client.get("/v1/billing").json()["plan"] == "plus"


def test_verified_cancellation_cannot_be_undone_by_an_old_approval(api_client, monkeypatch):
    from app.components.billing.worker import apply_payment

    client = api_client
    signin(client)
    configure(client)
    order = checkout(client)
    with client.app.state.sessions() as session:
        row = session.get(BillingOrder, order["orderId"])
        apply_payment(session, row, payment(order["orderId"]))
        session.commit()
        apply_payment(session, row, payment(order["orderId"], status="CANCELED"))
        session.commit()
        apply_payment(session, row, payment(order["orderId"]))
        session.commit()
        assert row.status == "cancelled"
    assert client.get("/v1/billing").json()["plan"] == "free"


def test_month_end_renewal_and_live_key_rejection():
    import pytest

    from app.components.billing.config import load_billing
    from app.components.billing.service import month_after

    assert month_after(datetime(2028, 1, 31, tzinfo=UTC)) == datetime(2028, 2, 29, tzinfo=UTC)
    with pytest.raises(ValueError):
        load_billing({"TOSS_CLIENT_KEY": "live_ck_wrong", "TOSS_SECRET_KEY": "live_sk_wrong"})


def test_unsubmitted_checkout_can_be_reopened_after_refresh(api_client):
    client = api_client
    signin(client)
    configure(client)
    order = checkout(client)
    reopened = checkout(client)
    assert reopened["orderId"] == order["orderId"]


def test_a_new_paid_period_restores_renewal_after_an_expired_cancelled_plan(api_client):
    from app.components.billing.worker import apply_payment

    client = api_client
    signin(client)
    configure(client)
    order = checkout(client)
    with client.app.state.sessions() as session:
        row = session.get(BillingOrder, order["orderId"])
        apply_payment(session, row, payment(order["orderId"]))
        session.commit()
        sub = session.scalar(select(Subscription))
        sub.cancel_at_period_end = True
        sub.period_end = datetime.now(UTC) - timedelta(seconds=1)
        session.commit()
        row.status = "paid"
    next_order = checkout(client)
    with client.app.state.sessions() as session:
        row = session.get(BillingOrder, next_order["orderId"])
        value = payment(next_order["orderId"])
        value["paymentKey"] = "second-fixture-payment"
        apply_payment(session, row, value)
        session.commit()
    summary = client.get("/v1/billing").json()
    assert summary["subscription"]["cancelAtPeriodEnd"] is False


def test_cancellation_during_a_pending_initial_approval_is_preserved(api_client):
    from app.components.billing.worker import apply_payment

    client = api_client
    signin(client)
    configure(client)
    order = checkout(client)
    assert post(client, "/v1/billing/cancel", {}).status_code == 200
    with client.app.state.sessions() as session:
        row = session.get(BillingOrder, order["orderId"])
        apply_payment(session, row, payment(order["orderId"]))
        session.commit()
    assert client.get("/v1/billing").json()["subscription"]["cancelAtPeriodEnd"] is True
