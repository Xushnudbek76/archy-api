import hmac
import re

import anyio
from fastapi import APIRouter, Request
from pydantic import BaseModel, ConfigDict, Field

from app.components.accounts.router import throttle
from app.components.billing.worker import reconcile
from app.libs.errors import ApiError

router = APIRouter(prefix="/v1/billing/events")


class EventInput(BaseModel):
    model_config = ConfigDict(extra="ignore", strict=True)
    eventType: str = Field(max_length=80)
    data: dict


@router.post("/{token}")
async def event(token: str, data: EventInput, request: Request):
    config = request.app.state.settings.billing
    if (
        not config.enabled
        or not config.webhook_token
        or len(token) > 128
        or not hmac.compare_digest(token, config.webhook_token)
    ):
        raise ApiError(404)
    throttle(request, "billing")
    key = data.data.get("orderId")
    if (
        data.eventType == "PAYMENT_STATUS_CHANGED"
        and isinstance(key, str)
        and re.fullmatch(r"archy_[0-9a-f]{32}", key)
    ):
        await anyio.to_thread.run_sync(
            reconcile,
            request.app.state.sessions,
            config,
            key,
            limiter=request.app.state.billing_limiter,
        )
    return {"received": True}
