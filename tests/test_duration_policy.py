import wave
from dataclasses import replace
from types import SimpleNamespace
from uuid import UUID

import pytest

from app.components.recordings.media import InvalidAudio, inspect_audio
from app.components.recordings.models import Upload
from tests.fastapi.test_accounts import post
from tests.fastapi.test_courses import signin
from tests.fastapi.test_recordings import admit, chunk


def write_audio(path, seconds, rate=8000):
    with wave.open(str(path), "wb") as target:
        target.setnchannels(1)
        target.setsampwidth(1)
        target.setframerate(rate)
        remaining = round(seconds * rate)
        while remaining:
            size = min(remaining, 65536)
            target.writeframesraw(b"\x80" * size)
            remaining -= size


@pytest.mark.parametrize("limit", [900, 1200])
@pytest.mark.parametrize("extra,accepted", [(0, True), (0.08, True), (1, True), (1.02, False)])
def test_one_second_duration_tolerance(tmp_path, limit, extra, accepted):
    path = tmp_path / "lecture.wav"
    write_audio(path, limit + extra)
    if accepted:
        assert inspect_audio(path, limit).duration_seconds == pytest.approx(
            limit + extra, abs=0.001
        )
    else:
        with pytest.raises(InvalidAudio) as error:
            inspect_audio(path, limit)
        assert error.value.code == "audio_too_long"


def test_policy_snapshot_survives_config_change(api_client):
    client = api_client
    signin(client)
    data, initial, _ = admit(client)
    assert initial["maxDurationSeconds"] == 1200
    client.app.state.settings = replace(client.app.state.settings, max_audio_duration_seconds=900)
    assert post(client, "/v1/uploads", data).json()["maxDurationSeconds"] == 1200
    assert client.get("/v1/uploads/" + initial["id"]).json()["maxDurationSeconds"] == 1200
    _, later, _ = admit(client)
    assert later["maxDurationSeconds"] == 900
    assert client.get("/v1/uploads/policy").json() == {"maxDurationSeconds": 900}
    from fastapi.testclient import TestClient

    from app.main import create_app

    application = create_app(client.app.state.settings)
    application.state.sessions = client.app.state.sessions
    with TestClient(application) as restarted:
        restarted.cookies.update(client.cookies)
        assert restarted.get("/v1/uploads/" + initial["id"]).json()["maxDurationSeconds"] == 1200


def test_legacy_upload_bypasses_new_cap(api_client):
    signin(api_client)
    from tests.fastapi.test_storage import audio_bytes

    _, upload, content = admit(api_client, audio_bytes(seconds=3))
    with api_client.app.state.sessions() as session:
        session.get(Upload, UUID(upload["id"])).max_duration_seconds = None
        session.commit()
    api_client.app.state.settings = replace(
        api_client.app.state.settings, max_audio_duration_seconds=1
    )
    assert chunk(api_client, upload["id"], 0, content).status_code == 200
    result = post(api_client, f"/v1/uploads/{upload['id']}/complete", {})
    assert result.status_code == 200 and result.json()["maxDurationSeconds"] is None


def test_terminal_duration_error_is_not_resumable(api_client):
    signin(api_client)
    api_client.app.state.settings = replace(
        api_client.app.state.settings, max_audio_duration_seconds=1
    )
    from tests.fastapi.test_storage import audio_bytes

    _, upload, content = admit(api_client, audio_bytes(seconds=3))
    chunk(api_client, upload["id"], 0, content)
    for _ in range(2):
        result = post(api_client, f"/v1/uploads/{upload['id']}/complete", {})
        assert result.status_code == 400 and result.json()["code"] == "audio_too_long"
    assert api_client.get("/v1/uploads").json()["items"] == []
    assert api_client.get("/v1/recordings").json()["items"] == []


def test_sample_fallback_stops_at_threshold_and_rejects_bad_rate():
    from app.components.recordings.probe import sample_duration

    def frames():
        for _ in range(3):
            yield SimpleNamespace(samples=48000, sample_rate=48000)
        raise AssertionError("Decoding must stop after crossing the threshold")

    with pytest.raises(ValueError, match="audio_too_long"):
        sample_duration(frames(), 1)
    with pytest.raises(ValueError, match="duration_unavailable"):
        sample_duration([SimpleNamespace(samples=48, sample_rate=0)], 1200)
    assert sample_duration([SimpleNamespace(samples=24000, sample_rate=48000)], 1200) == 0.5


def test_mediarecorder_without_duration_uses_sample_fallback():
    from pathlib import Path

    import av

    path = Path(__file__).parent / "fixtures/mediarecorder.webm"
    with av.open(str(path)) as source:
        assert source.duration is None
    legacy = inspect_audio(path)
    assert legacy.duration_seconds is None
    measured = inspect_audio(path, 1200)
    assert measured.content_type == "audio/webm"
    assert measured.duration_seconds is not None and 0.8 < measured.duration_seconds < 1.8


def test_duration_migration_keeps_existing_admissions_uncapped(prepared_database):
    import os
    from uuid import uuid4

    from alembic import command
    from dotenv import dotenv_values
    from sqlalchemy import create_engine, text
    from sqlalchemy.pool import NullPool

    from app.database.session import sqlalchemy_url
    from scripts.adopt_db import migration_config

    values = {**dotenv_values(".env.test"), **os.environ}
    engine = create_engine(
        sqlalchemy_url(values["TEST_MIGRATION_URL"], role="migration", test=True),
        poolclass=NullPool,
        hide_parameters=True,
        connect_args={"options": "-c search_path=archy"},
    )
    identifier = uuid4()
    try:
        with engine.connect() as connection, connection.begin():
            connection.execute(
                text(
                    "ALTER TABLE archy.recordings_upload DROP COLUMN IF EXISTS "
                    "max_duration_seconds CASCADE"
                )
            )
            connection.execute(text("UPDATE archy.alembic_version SET version_num='0002_auth'"))
            connection.execute(
                text(
                    "INSERT INTO "
                    "archy.accounts_user(id,email,password,display_name,is_active,is_staff,is_superuser,created_at,updated_at)"
                    " VALUES (:id,:email,'!synthetic','',true,false,false,now(),now())"
                ),
                {"id": identifier, "email": f"policy-{identifier}@example.com"},
            )
            connection.execute(
                text(
                    "INSERT INTO archy.courses_course(id,owner_id,title,created_at,updated_at) "
                    "VALUES (:id,:id,'Synthetic',now(),now())"
                ),
                {"id": identifier},
            )
            connection.execute(
                text(
                    "INSERT INTO "
                    "archy.recordings_upload(id,course_id,title,file_name,size_bytes,uploaded_bytes,sha256,status,error_code,created_at,updated_at)"
                    " VALUES "
                    "(:id,:id,'Synthetic','file.wav',10,0,:sha,'UPLOADING','',now(),now())"
                ),
                {"id": identifier, "sha": "a" * 64},
            )
            connection.execute(text("SET CONSTRAINTS ALL IMMEDIATE"))
            command.upgrade(migration_config(connection), "0003_duration_policy")
            assert connection.execute(
                text(
                    "SELECT max_duration_seconds,uploaded_bytes FROM archy.recordings_upload "
                    "WHERE id=:id"
                ),
                {"id": identifier},
            ).one() == (None, 0)
            assert (
                connection.execute(
                    text(
                        "SELECT column_default FROM information_schema.columns WHERE "
                        "table_schema='archy' AND table_name='recordings_upload' AND "
                        "column_name='max_duration_seconds'"
                    )
                ).scalar_one()
                is None
            )
            connection.rollback()
    finally:
        engine.dispose()


def test_sample_duration_accepts_exact_tolerance_without_rounding_drift():
    from app.components.recordings.probe import sample_duration

    frames = (SimpleNamespace(samples=800, sample_rate=8000) for _ in range(12010))
    assert sample_duration(frames, 1200) == 1201


def test_policy_probe_timeout_reports_unavailable(tmp_path, monkeypatch):
    import subprocess

    def timeout(*args, **kwargs):
        raise subprocess.TimeoutExpired("synthetic probe", 30)

    monkeypatch.setattr("app.components.recordings.media.subprocess.run", timeout)
    with pytest.raises(InvalidAudio) as error:
        inspect_audio(tmp_path / "synthetic.webm", 1200)
    assert error.value.code == "duration_unavailable"


@pytest.mark.parametrize("seconds", [900, 1200])
def test_real_browser_opus_sample_fallback_fits_probe_budget(tmp_path, seconds):
    import time
    from pathlib import Path

    import av

    from tests.browser_media import repeat_browser_audio

    path = tmp_path / "lecture.webm"
    repeat_browser_audio(Path(__file__).parent / "fixtures/mediarecorder.webm", path, seconds)
    with av.open(str(path)) as source:
        assert source.duration is None
    started = time.monotonic()
    result = inspect_audio(path, seconds)
    assert result.duration_seconds == pytest.approx(seconds, abs=0.08)
    assert time.monotonic() - started < 30


@pytest.mark.parametrize("seconds", [900, 1200])
@pytest.mark.parametrize(
    "extension,codec,container,sample_format,mime",
    [
        ("mp3", "libmp3lame", "mp3", "fltp", "audio/mpeg"),
        ("m4a", "aac", "mp4", "fltp", "audio/mp4"),
        ("flac", "flac", "flac", "s16", "audio/flac"),
        ("ogg", "libopus", "ogg", "s16", "audio/ogg"),
    ],
)
def test_supported_long_formats_fit_probe_budget(
    tmp_path, seconds, extension, codec, container, sample_format, mime
):
    import time

    from tests.browser_media import encode_audio

    path = tmp_path / ("lecture." + extension)
    encode_audio(path, seconds, codec, container, sample_format)
    started = time.monotonic()
    result = inspect_audio(path, seconds)
    assert result.content_type == mime
    assert result.duration_seconds == pytest.approx(seconds, abs=0.5)
    assert time.monotonic() - started < 30
