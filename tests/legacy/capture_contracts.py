import hashlib
import json
import tempfile
import uuid
from pathlib import Path


def shape(value):
    if isinstance(value, dict):
        return {key: shape(item) for key, item in sorted(value.items())}
    if isinstance(value, list):
        return [shape(value[0])] if value else []
    return type(value).__name__


def capture():
    from apps.accounts.models import SignupAttempt, User
    from apps.accounts.tokens import confirmation_token
    from apps.recordings.tests.test_storage import audio_bytes
    from django.contrib.auth.tokens import default_token_generator
    from django.db import connection, transaction
    from django.test import override_settings
    from django.utils.http import urlsafe_base64_encode
    from rest_framework.test import APIClient

    results = []
    client = APIClient(enforce_csrf_checks=True)

    def request(method, path, data=None, logical=None, **headers):
        if method not in {"get", "head"}:
            token = client.get("/v1/auth/csrf").json()["csrfToken"]
            headers["HTTP_X_CSRFTOKEN"] = token
        response = getattr(client, method)(path, data, format="json", **headers)
        results.append(
            {
                "method": method.upper(),
                "path": logical or path,
                "status": response.status_code,
                "body": shape(response.json())
                if not response.streaming and method != "head"
                else "binary",
                "cookies": {
                    name: {
                        key: cookie[key]
                        for key in ["httponly", "secure", "samesite", "path", "max-age"]
                    }
                    for name, cookie in response.cookies.items()
                },
            }
        )
        if response.streaming:
            list(response.streaming_content)
        return response

    with (
        tempfile.TemporaryDirectory() as directory,
        override_settings(
            RECORDING_STORAGE_ROOT=directory,
            EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
        ),
        transaction.atomic(),
    ):
        request("get", "/v1/health/live")
        request("get", "/v1/health/ready")
        request("get", "/v1/auth/csrf")
        request("get", "/v1/users/me")
        password = "Synthetic-safe-passphrase-827!"
        pending_email = f"capture-pending-{uuid.uuid4()}@example.com"
        request(
            "post",
            "/v1/auth/signup",
            {
                "email": pending_email,
                "password": password,
                "passwordConfirmation": password,
                "displayName": "Synthetic",
            },
        )
        attempt = SignupAttempt.objects.get(user__email=pending_email)
        request("post", "/v1/auth/confirm-email", {"token": confirmation_token(attempt)})
        user = User.objects.create_user(
            f"capture-{uuid.uuid4()}@example.com", password, is_active=True
        )
        request("post", "/v1/auth/password-reset", {"email": user.email})
        request(
            "post",
            "/v1/auth/password-reset/confirm",
            {
                "uid": urlsafe_base64_encode(str(user.pk).encode()),
                "token": default_token_generator.make_token(user),
                "password": password,
                "passwordConfirmation": password,
            },
        )
        request("post", "/v1/auth/login", {"email": user.email, "password": password})
        request("get", "/v1/users/me")
        course = request("post", "/v1/courses", {"title": "Synthetic course"}).json()
        request("get", "/v1/courses")
        request("patch", f"/v1/courses/{course['id']}", {"title": "Renamed"}, "/v1/courses/{id}")
        content = audio_bytes()
        upload = request(
            "post",
            "/v1/uploads",
            {
                "id": str(uuid.uuid4()),
                "courseId": course["id"],
                "title": "Synthetic lecture",
                "fileName": "lecture.wav",
                "sizeBytes": len(content),
                "sha256": hashlib.sha256(content).hexdigest(),
            },
        ).json()
        request("get", "/v1/uploads")
        request("get", f"/v1/uploads/{upload['id']}", logical="/v1/uploads/{id}")
        token = client.get("/v1/auth/csrf").json()["csrfToken"]
        chunk = client.patch(
            f"/v1/uploads/{upload['id']}/chunks",
            content,
            content_type="application/octet-stream",
            HTTP_X_CSRFTOKEN=token,
            HTTP_UPLOAD_OFFSET="0",
        )
        results.append(
            {
                "method": "PATCH",
                "path": "/v1/uploads/{id}/chunks",
                "status": chunk.status_code,
                "body": shape(chunk.json()),
                "cookies": {},
            }
        )
        saved = request(
            "post", f"/v1/uploads/{upload['id']}/complete", {}, "/v1/uploads/{id}/complete"
        ).json()
        request("get", "/v1/recordings")
        request(
            "get",
            f"/v1/recordings/{saved['recording']['id']}/audio",
            logical="/v1/recordings/{id}/audio",
            HTTP_RANGE="bytes=0-9",
        )
        for value in ["bytes=broken", "bytes=0-1,3-4", "bytes=999999-"]:
            request(
                "get",
                f"/v1/recordings/{saved['recording']['id']}/audio",
                logical="/v1/recordings/{id}/audio",
                HTTP_RANGE=value,
            )
            results[-1]["range"] = value
        request(
            "head",
            f"/v1/recordings/{saved['recording']['id']}/audio",
            logical="/v1/recordings/{id}/audio",
            HTTP_RANGE="bytes=0-1",
        )
        cancelled = request(
            "post",
            "/v1/uploads",
            {
                "id": str(uuid.uuid4()),
                "courseId": course["id"],
                "title": "Cancelled lecture",
                "fileName": "lecture.wav",
                "sizeBytes": len(content),
                "sha256": hashlib.sha256(content + b"cancelled").hexdigest(),
            },
        ).json()
        if "id" not in cancelled:
            raise ValueError(cancelled)
        request("post", f"/v1/uploads/{cancelled['id']}/cancel", {}, "/v1/uploads/{id}/cancel")
        request("post", f"/v1/courses/{course['id']}/archive", {}, "/v1/courses/{id}/archive")
        request("post", "/v1/auth/logout", {})
        transaction.set_rollback(True)

    columns = connection.cursor()
    with columns as cursor:
        cursor.execute(
            "SELECT table_name, column_name, data_type, udt_name, is_nullable, "
            "column_default, character_maximum_length FROM information_schema.columns "
            "WHERE table_schema='archy' ORDER BY table_name, ordinal_position"
        )
        column_metadata = [
            dict(zip([item[0] for item in cursor.description], row, strict=True))
            for row in cursor.fetchall()
        ]
        cursor.execute(
            "SELECT tablename, indexname, indexdef FROM pg_indexes WHERE "
            "schemaname='archy' ORDER BY tablename, indexname"
        )
        indexes = [
            dict(zip([item[0] for item in cursor.description], row, strict=True))
            for row in cursor.fetchall()
        ]
        cursor.execute(
            "SELECT c.relname AS table_name, con.conname AS name, "
            "pg_get_constraintdef(con.oid) AS definition, con.condeferrable, "
            "con.condeferred FROM pg_constraint con JOIN pg_class c ON "
            "c.oid=con.conrelid JOIN pg_namespace n ON n.oid=c.relnamespace WHERE "
            "n.nspname='archy' ORDER BY c.relname, con.conname"
        )
        constraints = [
            dict(zip([item[0] for item in cursor.description], row, strict=True))
            for row in cursor.fetchall()
        ]
    target = Path(__file__).parents[1] / "contracts"
    target.mkdir(parents=True, exist_ok=True)
    (target / "legacy-api.json").write_text(json.dumps(results, indent=2) + "\n")
    (target / "schema.json").write_text(
        json.dumps(
            {"columns": column_metadata, "indexes": indexes, "constraints": constraints}, indent=2
        )
        + "\n"
    )


if __name__ == "__main__":
    capture()
