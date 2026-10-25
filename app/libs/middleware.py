import re
import time
import uuid
from urllib.parse import urlsplit

from starlette.requests import Request

from app.libs.body import receive_body
from app.libs.errors import ApiError, error_response
from app.libs.logging import logger, report_error


class RequestMiddleware:
    def __init__(self, app, allowed_hosts):
        self.app = app
        self.allowed_hosts = set(allowed_hosts)

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        request_id = str(uuid.uuid4())
        scope.setdefault("state", {})["request_id"] = request_id
        started = time.monotonic()
        sent = False
        status = 500

        async def response_send(message):
            nonlocal sent, status
            if message["type"] == "http.response.start":
                sent, status = True, message["status"]
                headers = [
                    (key, value)
                    for key, value in message.get("headers", [])
                    if key.lower() not in {b"cache-control", b"x-request-id"}
                ]
                headers.extend(
                    [
                        (b"cache-control", b"private, no-store"),
                        (b"x-request-id", request_id.encode()),
                    ]
                )
                message = {**message, "headers": headers}
            await send(message)

        try:
            host = next(
                (
                    value.decode("latin-1")
                    for key, value in scope.get("headers", [])
                    if key.lower() == b"host"
                ),
                "",
            )
            if urlsplit("//" + host).hostname not in self.allowed_hosts:
                return await error_response(ApiError(400), request_id)(
                    scope, receive, response_send
                )
            headers = dict(scope.get("headers", []))
            chunk_route = scope["path"].startswith("/v1/uploads/") and scope["path"].endswith(
                "/chunks"
            )
            pdf_route = scope["method"] == "POST" and re.fullmatch(
                r"/v1/documents/[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}/pdf",
                scope["path"],
            )
            if scope["method"] in {"POST", "PUT", "PATCH"} and not (chunk_route or pdf_route):
                if (
                    headers.get(b"content-type", b"").split(b";")[0].strip().lower()
                    != b"application/json"
                ):
                    raise ApiError(415, "invalid_request", "Send a JSON request.")
                body = await receive_body(Request(scope, receive), 16384)
                original_receive = receive
                delivered = False

                async def buffered_receive():
                    nonlocal delivered
                    if not delivered:
                        delivered = True
                        return {"type": "http.request", "body": body, "more_body": False}
                    return await original_receive()

                receive = buffered_receive
            await self.app(scope, receive, response_send)
        except ApiError as error:
            if sent:
                raise RuntimeError("Private response stream terminated") from None
            await error_response(error, request_id)(scope, receive, response_send)
        except Exception as error:
            report_error(error, request_id)
            if sent:
                raise RuntimeError("Private response stream terminated") from None
            await error_response(ApiError(500), request_id)(scope, receive, response_send)
        finally:
            route = scope.get("route")
            logger.info(
                {
                    "event": "request",
                    "request_id": request_id,
                    "method": scope["method"],
                    "route": getattr(route, "path", "unmatched"),
                    "status": status,
                    "duration_ms": round((time.monotonic() - started) * 1000, 2),
                }
            )
