from uuid import uuid4

from apps.core.errors import error_response


class RequestMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        request.request_id = str(uuid4())
        response = self.get_response(request)
        if request.path.startswith("/v1/"):
            if (
                response.status_code >= 400
                and response.get("Content-Type", "").split(";")[0] != "application/json"
            ):
                response = error_response(request, response.status_code)
            response["X-Request-ID"] = request.request_id
            response["Cache-Control"] = "private, no-store"
        return response

    def process_exception(self, request, exception):
        if request.path.startswith("/v1/"):
            return error_response(request, 500)
