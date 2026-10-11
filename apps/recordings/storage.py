import hashlib
import os
import shutil
import tempfile
import uuid
from pathlib import Path


class StorageConflict(Exception):
    pass


class LocalRecordingStorage:
    def __init__(self, root):
        self.root = Path(root).resolve()

    def _directory(self, name):
        path = self.root / name
        path.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.root.chmod(0o700)
        path.chmod(0o700)
        return path

    def upload_directory(self, key):
        return self._directory("uploads") / str(uuid.UUID(str(key)))

    def recording_path(self, key):
        return self.root / "recordings" / (str(uuid.UUID(str(key))) + ".audio")

    def available_bytes(self):
        self._directory("uploads")
        return shutil.disk_usage(self.root).free

    def write_part(self, key, offset, data):
        if not isinstance(offset, int) or offset < 0:
            raise ValueError("Invalid offset")
        directory = self.upload_directory(key)
        directory.mkdir(exist_ok=True, mode=0o700)
        path = directory / f"{offset}.part"
        if path.exists():
            if path.read_bytes() != data:
                raise StorageConflict
            return
        descriptor, temporary = tempfile.mkstemp(dir=directory)
        try:
            with os.fdopen(descriptor, "wb") as target:
                target.write(data)
                target.flush()
                os.fsync(target.fileno())
            os.replace(temporary, path)
        finally:
            Path(temporary).unlink(missing_ok=True)

    def assemble(self, key):
        directory = self.upload_directory(key)
        for temporary in directory.glob("tmp*"):
            temporary.unlink(missing_ok=True)
        for existing in (directory / "assembled", self.recording_path(key)):
            if existing.is_file():
                digest = hashlib.sha256()
                size = 0
                with existing.open("rb") as source:
                    while block := source.read(1024 * 1024):
                        digest.update(block)
                        size += len(block)
                return existing, digest.hexdigest(), size
        digest = hashlib.sha256()
        size = 0
        parts = sorted(directory.glob("*.part"), key=lambda part: int(part.stem))
        descriptor, temporary = tempfile.mkstemp(dir=directory)
        try:
            with os.fdopen(descriptor, "wb") as target:
                for part in parts:
                    if int(part.stem) != size:
                        raise StorageConflict
                    with part.open("rb") as source:
                        while block := source.read(1024 * 1024):
                            target.write(block)
                            digest.update(block)
                            size += len(block)
                target.flush()
                os.fsync(target.fileno())
            path = directory / "assembled"
            os.replace(temporary, path)
            return path, digest.hexdigest(), size
        finally:
            Path(temporary).unlink(missing_ok=True)

    def publish(self, key, source):
        self._directory("recordings")
        os.replace(source, self.recording_path(key))

    def remove_upload(self, key):
        shutil.rmtree(self.upload_directory(key), ignore_errors=True)
