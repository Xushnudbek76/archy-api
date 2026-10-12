from starlette.responses import JSONResponse

MESSAGES = {
    400: ("invalid_request", "Check the request fields."),
    401: ("unauthenticated", "Authentication required."),
    403: ("forbidden", "Request not permitted."),
    404: ("not_found", "Resource not found."),
    405: ("method_not_allowed", "Method not allowed."),
    408: ("upload_timeout", "Upload paused because the connection stopped."),
    413: ("invalid_chunk", "The request is too large."),
    429: ("rate_limited", "Too many requests. Try again later."),
    500: ("server_error", "The request could not be completed."),
    503: ("not_ready", "Service temporarily unavailable."),
}


class ApiError(Exception):
    def __init__(self, status, code=None, message=None, *, retry_after=None):
        default_code, default_message = MESSAGES.get(status, MESSAGES[500])
        self.status = status
        self.code = code or default_code
        self.message = message or default_message
        self.retry_after = retry_after
        super().__init__(self.code)


def error_response(error, request_id):
    headers = {"Cache-Control": "private, no-store", "X-Request-ID": request_id}
    if error.retry_after is not None:
        headers["Retry-After"] = str(error.retry_after)
    return JSONResponse(
        {"code": error.code, "message": error.message, "requestId": request_id},
        status_code=error.status,
        headers=headers,
    )
