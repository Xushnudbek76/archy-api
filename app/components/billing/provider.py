import time
from urllib.parse import quote

import httpx

from app.libs.errors import ApiError


def request(config, method, path, body=None, key=None):
    if not config.enabled or not config.secret_key.startswith("test_sk_"):
        raise ApiError(503, "billing_disabled", "Test billing is not configured.")
    headers = {"Idempotency-Key": key} if key else {}
    started = time.monotonic()
    try:
        with (
            httpx.Client(
                timeout=httpx.Timeout(65, connect=10),
                follow_redirects=False,
                trust_env=False,
                auth=(config.secret_key, ""),
            ) as client,
            client.stream(
                method, "https://api.tosspayments.com/v1" + path, json=body, headers=headers
            ) as response,
        ):
            if response.status_code == 404 and method == "GET":
                return None
            response.raise_for_status()
            content = bytearray()
            for part in response.iter_bytes():
                content.extend(part)
                if len(content) > 131072 or time.monotonic() - started > 75:
                    raise ValueError("Oversized payment response")
        if method == "DELETE":
            return {}
        import json

        value = json.loads(content)
        if not isinstance(value, dict):
            raise ValueError("Invalid payment response")
        return value
    except (httpx.HTTPError, ValueError):
        raise ApiError(
            503,
            "payment_pending",
            "Payment could not be verified yet. Check its status before retrying.",
        ) from None


def order_path(order_id):
    return "/payments/orders/" + quote(order_id, safe="")


def billing_path(key):
    return "/billing/" + quote(key, safe="")
