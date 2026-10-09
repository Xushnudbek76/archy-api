from django.db import DatabaseError, connection
from django.http import JsonResponse
from django.views.decorators.http import require_GET

from apps.core.errors import error_response


@require_GET
def live(request):
    return JsonResponse({"status": "ok"})


@require_GET
def ready(request):
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT id FROM accounts_user LIMIT 1")
            cursor.execute("SELECT id FROM courses_course LIMIT 1")
    except DatabaseError:
        return error_response(request, 503)
    return JsonResponse({"status": "ok"})


def csrf_failure(request, reason=""):
    return error_response(request, 403)
