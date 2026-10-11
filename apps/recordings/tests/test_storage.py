import hashlib
import io
import uuid
import wave

import pytest


def audio_bytes(seconds=1, rate=8000):
    target = io.BytesIO()
    with wave.open(target, "wb") as audio:
        audio.setnchannels(1)
        audio.setsampwidth(1)
        audio.setframerate(rate)
        audio.writeframes(b"\x80" * rate * seconds)
    return target.getvalue()


def test_atomic_chunks_assemble_and_match_checksum(tmp_path):
    from apps.recordings.storage import LocalRecordingStorage

    storage = LocalRecordingStorage(tmp_path)
    key = uuid.uuid4()
    storage.write_part(key, 0, b"first")
    storage.write_part(key, 5, b"last")
    storage.write_part(key, 0, b"first")
    path, checksum, size = storage.assemble(key)
    assert path.read_bytes() == b"firstlast"
    assert checksum == hashlib.sha256(b"firstlast").hexdigest()
    assert size == 9
    storage.publish(key, path)
    assert storage.recording_path(key).read_bytes() == b"firstlast"
    storage.remove_upload(key)
    assert storage.recording_path(key).read_bytes() == b"firstlast"
    assert not (tmp_path / "uploads" / str(key)).exists()
    assert storage.recording_path(key).stat().st_mode & 0o777 == 0o600


def test_mismatched_replay_and_noncontiguous_parts_do_not_publish(tmp_path):
    from apps.recordings.storage import LocalRecordingStorage, StorageConflict

    storage = LocalRecordingStorage(tmp_path)
    key = uuid.uuid4()
    storage.write_part(key, 0, b"first")
    with pytest.raises(StorageConflict):
        storage.write_part(key, 0, b"wrong")
    storage.write_part(key, 8, b"gap")
    with pytest.raises(StorageConflict):
        storage.assemble(key)
    assert not storage.recording_path(key).exists()
    assert (tmp_path / "uploads" / str(key) / "0.part").read_bytes() == b"first"


def test_storage_rejects_caller_paths(tmp_path):
    from apps.recordings.storage import LocalRecordingStorage

    with pytest.raises(ValueError):
        LocalRecordingStorage(tmp_path).recording_path("../../secret")


def test_probe_actual_audio_ignores_misleading_extension(tmp_path):
    from apps.recordings.media import inspect_audio

    path = tmp_path / "wrong.mp3"
    path.write_bytes(audio_bytes())
    result = inspect_audio(path)
    assert result["content_type"] == "audio/wav"
    assert result["duration_seconds"] == pytest.approx(1)


def test_hours_long_audio_has_no_duration_cap(tmp_path):
    from apps.recordings.media import inspect_audio

    path = tmp_path / "long.wav"
    path.write_bytes(audio_bytes(seconds=3 * 3600, rate=1000))
    result = inspect_audio(path)
    assert result["duration_seconds"] == pytest.approx(10800)


@pytest.mark.parametrize("content", [b"", b"<html>not audio</html>", b"RIFFnot a valid WAV"])
def test_invalid_media_rejected(tmp_path, content):
    from apps.recordings.media import InvalidAudio, inspect_audio

    path = tmp_path / "fake.wav"
    path.write_bytes(content)
    with pytest.raises(InvalidAudio):
        inspect_audio(path)


@pytest.mark.parametrize("published", [False, True])
def test_completion_retry_reuses_existing_copy(tmp_path, monkeypatch, published):
    from apps.recordings.storage import LocalRecordingStorage

    storage = LocalRecordingStorage(tmp_path)
    key = uuid.uuid4()
    storage.write_part(key, 0, b"audio")
    path, checksum, size = storage.assemble(key)
    if published:
        storage.publish(key, path)

    def no_extra_copy(*args, **kwargs):
        raise AssertionError("Retry must not allocate a third full copy")

    monkeypatch.setattr("apps.recordings.storage.tempfile.mkstemp", no_extra_copy)
    recovered, recovered_checksum, recovered_size = storage.assemble(key)
    assert recovered.read_bytes() == b"audio"
    assert (recovered_checksum, recovered_size) == (checksum, size)
