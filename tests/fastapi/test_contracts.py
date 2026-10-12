import hashlib
import json
from http.cookies import SimpleCookie
from pathlib import Path
from uuid import uuid4

from tests.fastapi.test_accounts import PASSWORD, link, post
from tests.fastapi.test_storage import audio_bytes
from tests.legacy.capture_contracts import shape


def normalized_cookies(cookies):
    return {
        name: {
            "httponly": bool(value["httponly"]),
            "secure": bool(value["secure"]),
            "samesite": value["samesite"].lower(),
            "path": value["path"],
            "max-age": int(value["max-age"]) if value["max-age"] != "" else "",
        }
        for name, value in cookies.items()
    }


def legacy_shape(value):
    if isinstance(value, dict):
        value = {
            key: legacy_shape(item) for key, item in value.items() if key != "maxDurationSeconds"
        }
    elif isinstance(value, list):
        value = [legacy_shape(item) for item in value]
    return value


def test_corrected_api_contracts_match(api_client):
    client = api_client
    results = []

    def capture(method, path, data=None, logical=None, **headers):
        response = (
            post(client, path, data)
            if method == "POST"
            else client.request(method, path, json=data, headers=headers)
        )
        if method == "PATCH" and not path.endswith("/chunks"):
            csrf = client.get("/v1/auth/csrf").json()["csrfToken"]
            response = client.patch(path, json=data, headers={"X-CSRFToken": csrf})
        cookies = SimpleCookie()
        for value in response.headers.get_list("set-cookie"):
            cookies.load(value)
        binary = path.endswith("/audio") and response.status_code != 416
        results.append(
            {
                "method": method,
                "path": logical or path,
                "status": response.status_code,
                "body": "binary" if binary else shape(legacy_shape(response.json())),
                "cookies": normalized_cookies(cookies),
            }
        )
        if "Range" in headers and headers["Range"] != "bytes=0-9" and method == "GET":
            results[-1]["range"] = headers["Range"]
        return response

    capture("GET", "/v1/health/live")
    capture("GET", "/v1/health/ready")
    capture("GET", "/v1/auth/csrf")
    capture("GET", "/v1/users/me")
    capture(
        "POST",
        "/v1/auth/signup",
        {
            "email": "contract@example.com",
            "password": PASSWORD,
            "passwordConfirmation": PASSWORD,
            "displayName": "Synthetic",
        },
    )
    capture("POST", "/v1/auth/confirm-email", link(client))
    capture("POST", "/v1/auth/password-reset", {"email": "contract@example.com"})
    capture(
        "POST",
        "/v1/auth/password-reset/confirm",
        {**link(client), "password": PASSWORD, "passwordConfirmation": PASSWORD},
    )
    capture("POST", "/v1/auth/login", {"email": "contract@example.com", "password": PASSWORD})
    capture("GET", "/v1/users/me")
    course = capture("POST", "/v1/courses", {"title": "Synthetic course"}).json()
    capture("GET", "/v1/courses")
    capture("PATCH", f"/v1/courses/{course['id']}", {"title": "Renamed"}, "/v1/courses/{id}")
    content = audio_bytes()
    data = {
        "id": str(uuid4()),
        "courseId": course["id"],
        "title": "Synthetic lecture",
        "fileName": "lecture.wav",
        "sizeBytes": len(content),
        "sha256": hashlib.sha256(content).hexdigest(),
    }
    upload = capture("POST", "/v1/uploads", data).json()
    capture("GET", "/v1/uploads")
    capture("GET", f"/v1/uploads/{upload['id']}", logical="/v1/uploads/{id}")
    csrf = client.get("/v1/auth/csrf").json()["csrfToken"]
    chunk = client.patch(
        f"/v1/uploads/{upload['id']}/chunks",
        content=content,
        headers={
            "Content-Type": "application/octet-stream",
            "X-CSRFToken": csrf,
            "Upload-Offset": "0",
        },
    )
    results.append(
        {
            "method": "PATCH",
            "path": "/v1/uploads/{id}/chunks",
            "status": chunk.status_code,
            "body": shape(legacy_shape(chunk.json())),
            "cookies": {},
        }
    )
    saved = capture(
        "POST", f"/v1/uploads/{upload['id']}/complete", {}, "/v1/uploads/{id}/complete"
    ).json()
    capture("GET", "/v1/recordings")
    audio = f"/v1/recordings/{saved['recording']['id']}/audio"
    for value in ["bytes=0-9", "bytes=broken", "bytes=0-1,3-4", "bytes=999999-"]:
        capture("GET", audio, logical="/v1/recordings/{id}/audio", Range=value)
    capture("HEAD", audio, logical="/v1/recordings/{id}/audio", Range="bytes=0-1")
    cancelled = capture(
        "POST",
        "/v1/uploads",
        {
            **data,
            "id": str(uuid4()),
            "title": "Cancelled lecture",
            "sha256": hashlib.sha256(content + b"cancelled").hexdigest(),
        },
    ).json()
    capture("POST", f"/v1/uploads/{cancelled['id']}/cancel", {}, "/v1/uploads/{id}/cancel")
    capture("POST", f"/v1/courses/{course['id']}/archive", {}, "/v1/courses/{id}/archive")
    capture("POST", "/v1/auth/logout", {})
    expected = json.loads((Path(__file__).parents[1] / "contracts/legacy-api.json").read_text())
    for item in expected:
        item["cookies"] = normalized_cookies(item["cookies"])
    # The approved cookie policy keeps HttpOnly on deletion as well as issuance.
    expected[-1]["cookies"]["sessionid"]["httponly"] = True
    assert results == expected
