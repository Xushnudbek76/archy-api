from django.http import JsonResponse
from rest_framework.exceptions import APIException
from rest_framework.views import exception_handler as drf_exception_handler


class ClientError(APIException):
    def __init__(self, status, code, message):
        self.status_code = status
        self.public_code = code
        self.public_message = message
        super().__init__(message)


MESSAGES = {
    400: ("invalid_request", "Check the request fields."),
    401: ("unauthenticated", "Authentication required."),
    403: ("forbidden", "Request not permitted."),
    404: ("not_found", "Resource not found."),
    405: ("method_not_allowed", "Method not allowed."),
    429: ("rate_limited", "Too many requests. Try again later."),
    500: ("server_error", "The request could not be completed."),
    503: ("not_ready", "Service temporarily unavailable."),
}


def error_response(request, status):
    code, message = MESSAGES.get(status, MESSAGES[500])
    return JsonResponse(
        {"code": code, "message": message, "requestId": getattr(request, "request_id", "")},
        status=status,
    )


def exception_handler(exc, context):
    response = drf_exception_handler(exc, context)
    status = response.status_code if response is not None else 500
    if response is None:
        return error_response(context["request"], status)
    code, message = (
        (exc.public_code, exc.public_message)
        if isinstance(exc, ClientError)
        else MESSAGES.get(status, MESSAGES[500])
    )
    response.data = {"code": code, "message": message, "requestId": context["request"].request_id}
    return response
