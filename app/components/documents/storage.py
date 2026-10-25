import os
import stat
from pathlib import Path
from uuid import UUID


class DocumentStorage:
    def __init__(self, root):
        self.root = Path(root)
        self.directory = None

    def __enter__(self):
        self.root.mkdir(parents=True, exist_ok=True, mode=0o700)
        root = os.open(self.root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        try:
            os.fchmod(root, 0o700)
            try:
                os.mkdir("documents", mode=0o700, dir_fd=root)
            except FileExistsError:
                pass
            self.directory = os.open(
                "documents", os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=root
            )
            os.fchmod(self.directory, 0o700)
        finally:
            os.close(root)
        return self

    def __exit__(self, *args):
        os.close(self.directory)

    def name(self, key):
        return f"{UUID(str(key))}.pdf"

    def publish(self, key, body):
        descriptor = os.open(
            self.name(key),
            os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
            0o600,
            dir_fd=self.directory,
        )
        try:
            with os.fdopen(descriptor, "wb") as target:
                target.write(body)
                target.flush()
                os.fsync(target.fileno())
        except BaseException:
            self.remove(key)
            raise

    def remove(self, key):
        os.unlink(self.name(key), dir_fd=self.directory)

    def open(self, key, size):
        descriptor = os.open(
            self.name(key), os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=self.directory
        )
        metadata = os.fstat(descriptor)
        if not stat.S_ISREG(metadata.st_mode) or metadata.st_size != size:
            os.close(descriptor)
            raise OSError("Private PDF is unavailable")
        return descriptor
