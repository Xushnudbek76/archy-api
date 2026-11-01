import fcntl
import os
import shutil
import tempfile
from contextlib import contextmanager
from pathlib import Path
from uuid import UUID


@contextmanager
def processing_lock(root, key):
    folder = Path(root) / ".processing-locks"
    folder.mkdir(parents=True, exist_ok=True, mode=0o700)
    descriptor = os.open(folder, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    lock = None
    try:
        lock = os.open(
            str(UUID(str(key))) + ".lock",
            os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW,
            0o600,
            dir_fd=descriptor,
        )
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        yield
    finally:
        if lock is not None:
            os.close(lock)
        os.close(descriptor)


@contextmanager
def processing_workspace(sessions, settings, held):
    from app.components.processing.queue import LeaseLost, mutate

    try:
        with processing_lock(settings.storage_root, held.id):
            mutate(sessions, held, lambda session, job: None)
            root = settings.storage_root / "processing"
            root.mkdir(parents=True, exist_ok=True, mode=0o700)
            root.chmod(0o700)
            directory = Path(tempfile.mkdtemp(prefix=f"{held.id}-{held.token}-", dir=root))
            try:
                yield directory
            finally:
                shutil.rmtree(directory, ignore_errors=True)
    except BlockingIOError:
        raise LeaseLost from None
