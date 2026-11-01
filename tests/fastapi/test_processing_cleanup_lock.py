from uuid import uuid4

from app.libs.processing_files import processing_lock
from scripts.run_worker import cleanup


def test_idle_cleanup_does_not_race_an_owned_processing_directory(api_client):
    root = api_client.app.state.settings.storage_root
    key = uuid4()
    directory = root / "processing" / f"{key}-{uuid4()}-orphan"
    directory.mkdir(parents=True)
    (directory / "part.flac").write_bytes(b"private")
    with processing_lock(root, key):
        cleanup(api_client.app.state.sessions, root / "processing")
        assert directory.is_dir()
    cleanup(api_client.app.state.sessions, root / "processing")
    assert not directory.exists()
