import pytest

from app.libs.errors import ApiError
from app.libs.throttling import AccountLimiter


def test_next_proxy_login_limit_is_a_shared_bucket():
    limiter = AccountLimiter()
    for _ in range(10):
        limiter.check("login", "127.0.0.1")
    with pytest.raises(ApiError) as error:
        limiter.check("login", "127.0.0.1")
    assert error.value.status == 429
    assert 1 <= error.value.retry_after <= 60
    limiter.check("login", "other-peer")


def test_limiter_evicts_expired_buckets_and_is_bounded(monkeypatch):
    current = 0
    monkeypatch.setattr("app.libs.throttling.time.monotonic", lambda: current)
    limiter = AccountLimiter()
    for _ in range(3):
        limiter.check("signup", "shared-peer")
    current = 3601
    limiter.check("signup", "shared-peer")
    assert len(limiter.buckets[("signup", "shared-peer")]) == 1
    for index in range(10001):
        limiter.check("login", str(index))
    assert len(limiter.buckets) == 10000
