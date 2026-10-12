import asyncio
import hashlib
import socket
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from datetime import timedelta
from urllib.error import HTTPError
from urllib.request import urlopen
from uuid import uuid4

import pytest
import uvicorn
from sqlalchemy import delete

from app.components.accounts.models import AccountSession, SignupAttempt, User, now
from app.components.courses.models import Course
from app.components.recordings.models import Recording, Upload
from app.components.recordings.storage import LocalRecordingStorage
from app.database.session import session_factory
from app.libs.security import digest_token
from app.main import create_app


@contextmanager
def running_server(settings):
    app = create_app(settings)
    listener = socket.socket()
    listener.bind(("127.0.0.1", 0))
    listener.listen(128)
    port = listener.getsockname()[1]
    server = uvicorn.Server(
        uvicorn.Config(app, host="127.0.0.1", port=port, access_log=False, log_level="error")
    )
    thread = threading.Thread(
        target=lambda: asyncio.run(server.serve(sockets=[listener])), daemon=True
    )
    thread.start()
    deadline = time.monotonic() + 5
    while not server.started:
        if time.monotonic() > deadline:
            raise RuntimeError("Test server did not start")
        time.sleep(0.01)
    try:
        yield app, port
    finally:
        server.should_exit = True
        thread.join(timeout=5)
        listener.close()
        assert not thread.is_alive()


def status(port, path):
    try:
        with urlopen(f"http://127.0.0.1:{port}{path}", timeout=5) as response:
            return response.status
    except HTTPError as error:
        return error.code


def headers_socket(port, path, token, *, chunk=False):
    client = socket.create_connection(("127.0.0.1", port), timeout=5)
    headers = f"Host: 127.0.0.1:{port}\r\nCookie: sessionid={token}\r\n"
    method = "GET"
    if chunk:
        method = "PATCH"
        headers += (
            "Content-Type: application/octet-stream\r\nContent-Length: 100\r\nUpload-Offset: 0\r\n"
        )
    client.sendall(f"{method} {path} HTTP/1.1\r\n{headers}\r\n".encode())
    return client


@pytest.fixture
def streaming_data(settings, prepared_database):
    from app.database.session import create_engine_for
    from app.libs.security import issue_csrf

    engine = create_engine_for(settings)
    sessions = session_factory(engine)
    user_id, course_id, upload_id, recording_id = uuid4(), uuid4(), uuid4(), uuid4()
    token = uuid4().hex + uuid4().hex
    content = b"x" * (8 * 1024 * 1024)
    disk = LocalRecordingStorage(settings.storage_root)
    disk._directory("recordings")
    disk.recording_path(recording_id).write_bytes(content)
    with sessions() as session:
        session.add(
            User(
                id=user_id,
                email=f"concurrency-{user_id}@example.com",
                password="!synthetic",
                is_active=True,
            )
        )
        session.flush()
        session.add(Course(id=course_id, owner_id=user_id, title="Synthetic"))
        session.add(
            Upload(
                id=upload_id,
                course_id=course_id,
                title="Pending",
                file_name="pending.wav",
                size_bytes=100,
                sha256=hashlib.sha256(b"x" * 100).hexdigest(),
            )
        )
        session.add(
            Upload(
                id=recording_id,
                course_id=course_id,
                title="Accepted",
                file_name="accepted.wav",
                size_bytes=len(content),
                uploaded_bytes=len(content),
                sha256=hashlib.sha256(content).hexdigest(),
                status="ACCEPTED",
            )
        )
        session.add(
            Recording(
                id=recording_id,
                course_id=course_id,
                upload_id=recording_id,
                title="Accepted",
                size_bytes=len(content),
                sha256=hashlib.sha256(content).hexdigest(),
                content_type="audio/wav",
            )
        )
        session.flush()
        session.add(
            AccountSession(
                user_id=user_id, digest=digest_token(token), expires_at=now() + timedelta(days=1)
            )
        )
        session.commit()
    try:
        yield token, upload_id, recording_id, issue_csrf(settings.secret_key)
    finally:
        with sessions() as session:
            session.execute(delete(Recording).where(Recording.course_id == course_id))
            session.execute(delete(Upload).where(Upload.course_id == course_id))
            session.execute(delete(Course).where(Course.id == course_id))
            session.execute(delete(SignupAttempt).where(SignupAttempt.user_id == user_id))
            session.execute(delete(User).where(User.id == user_id))
            session.commit()
        engine.dispose()


def test_open_stream_and_pool_saturation_do_not_block_liveness(settings, streaming_data):
    token, upload_id, recording_id, _ = streaming_data
    with running_server(settings) as (app, port):
        stream = headers_socket(port, f"/v1/recordings/{recording_id}/audio", token)
        try:
            assert b"200 OK" in stream.recv(1024)
            connections = [app.state.engine.connect() for _ in range(5)]
            try:
                assert app.state.engine.pool.checkedout() == 5
                with ThreadPoolExecutor() as executor:
                    readiness = executor.submit(status, port, "/v1/health/ready")
                    started = time.monotonic()
                    assert status(port, "/v1/health/live") == 200
                    assert time.monotonic() - started < 0.5
                    assert readiness.result(timeout=5) == 503
            finally:
                for connection in connections:
                    connection.close()
        finally:
            stream.close()


def test_fifth_authorized_chunk_receives_429_without_body_and_disconnect_releases_slots(
    settings, streaming_data
):
    from app.components.recordings.models import Upload

    token, upload_id, _, csrf = streaming_data
    with running_server(settings) as (app, port):
        clients = []

        def open_chunk():
            client = socket.create_connection(("127.0.0.1", port), timeout=5)
            client.sendall(
                (
                    f"PATCH /v1/uploads/{upload_id}/chunks HTTP/1.1\r\n"
                    f"Host: 127.0.0.1:{port}\r\n"
                    f"Cookie: sessionid={token}; csrftoken={csrf}\r\n"
                    f"X-CSRFToken: {csrf}\r\nOrigin: {settings.frontend_origin}\r\n"
                    "Content-Type: application/octet-stream\r\n"
                    "Content-Length: 100\r\nUpload-Offset: 0\r\n\r\n"
                ).encode()
            )
            return client

        try:
            clients = [open_chunk() for _ in range(4)]
            deadline = time.monotonic() + 3
            while app.state.chunk_limiter.borrowed_tokens != 4:
                assert time.monotonic() < deadline
                time.sleep(0.01)
            assert app.state.engine.pool.checkedout() == 0
            fifth = open_chunk()
            try:
                response = fifth.recv(2048)
                assert b"429 Too Many Requests" in response
                assert b"retry-after: 2" in response.lower()
            finally:
                fifth.close()
            assert status(port, "/v1/health/live") == 200
        finally:
            for client in clients:
                client.close()
        deadline = time.monotonic() + 3
        while app.state.chunk_limiter.borrowed_tokens:
            assert time.monotonic() < deadline
            time.sleep(0.01)
        with app.state.sessions() as session:
            assert session.get(Upload, upload_id).uploaded_bytes == 0
