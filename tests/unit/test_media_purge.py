from uuid import uuid4

import pytest

from app.components.preferences.purge import purge_media


def test_account_media_purge_only_unlinks_named_files_and_never_follows_directories(tmp_path):
    root = tmp_path / "media"
    (root / "documents").mkdir(parents=True)
    owned, other = uuid4(), uuid4()
    (root / "documents" / f"{owned}.pdf").write_bytes(b"owned")
    untouched = root / "documents" / f"{other}.pdf"
    untouched.write_bytes(b"other")
    media = {"documents": [str(owned)], "recordings": [], "uploads": []}
    purge_media(root, media)
    purge_media(root, media)
    assert untouched.read_bytes() == b"other"
    uploads = root / "uploads"
    uploads.mkdir()
    external = tmp_path / "external"
    external.mkdir()
    (external / "private").write_bytes(b"keep")
    upload = uuid4()
    (uploads / str(upload)).symlink_to(external, target_is_directory=True)
    with pytest.raises(OSError):
        purge_media(root, {"documents": [], "recordings": [], "uploads": [str(upload)]})
    assert (external / "private").read_bytes() == b"keep"


def test_processing_cleanup_waits_for_the_active_job_and_keeps_other_jobs(tmp_path):
    from app.libs.processing_files import processing_lock

    root = tmp_path / "media"
    processing = root / "processing"
    processing.mkdir(parents=True)
    job, other = uuid4(), uuid4()
    owned = processing / f"{job}-{uuid4()}-orphan"
    owned.mkdir()
    (owned / "part.flac").write_bytes(b"private")
    untouched = processing / f"{other}-{uuid4()}-other"
    untouched.mkdir()
    (untouched / "part.flac").write_bytes(b"other")
    media = {"jobs": [str(job)], "documents": [], "recordings": [], "uploads": []}
    with processing_lock(root, job):
        with pytest.raises(BlockingIOError):
            purge_media(root, media)
        assert owned.is_dir()
    purge_media(root, media)
    assert not owned.exists() and (untouched / "part.flac").read_bytes() == b"other"
