import os
import stat
from contextlib import contextmanager
from datetime import timedelta
from uuid import UUID

from sqlalchemy import select

from app.components.accounts.models import now
from app.components.preferences.models import MediaPurge
from app.libs.logging import logger
from app.libs.processing_files import processing_lock


@contextmanager
def directory(name, parent=None):
    descriptor = os.open(name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=parent)
    try:
        yield descriptor
    finally:
        os.close(descriptor)


def unlink(parent, name):
    try:
        os.unlink(name, dir_fd=parent)
    except FileNotFoundError:
        pass


def purge_media(root, media):
    try:
        with directory(root) as parent:
            for key in media.get("jobs", []):
                with processing_lock(root, key):
                    try:
                        with directory("processing", parent) as processing:
                            for name in os.listdir(processing):
                                if name.startswith(str(UUID(key)) + "-"):
                                    with directory(name, processing) as child:
                                        clear_directory(child)
                                    os.rmdir(name, dir_fd=processing)
                    except FileNotFoundError:
                        pass
            for kind, extension in [("documents", ".pdf"), ("recordings", ".audio")]:
                try:
                    with directory(kind, parent) as folder:
                        for key in media[kind]:
                            unlink(folder, str(UUID(key)) + extension)
                except FileNotFoundError:
                    pass
            try:
                with directory("uploads", parent) as uploads:
                    for key in media["uploads"]:
                        name = str(UUID(key))
                        try:
                            with directory(name, uploads) as folder:
                                for entry in os.listdir(folder):
                                    unlink(folder, entry)
                            os.rmdir(name, dir_fd=uploads)
                        except FileNotFoundError:
                            pass
            except FileNotFoundError:
                pass
    except FileNotFoundError:
        pass


def clear_directory(parent, depth=0):
    if depth > 8:
        raise OSError("Unexpected processing directory depth")
    for name in os.listdir(parent):
        details = os.stat(name, dir_fd=parent, follow_symlinks=False)
        if stat.S_ISDIR(details.st_mode):
            with directory(name, parent) as child:
                clear_directory(child, depth + 1)
            os.rmdir(name, dir_fd=parent)
        else:
            unlink(parent, name)


def purge_once(sessions, root, key=None):
    with sessions.begin() as session:
        query = select(MediaPurge).where(MediaPurge.available_at <= now(), MediaPurge.attempts < 8)
        if key is not None:
            query = query.where(MediaPurge.id == key)
        task = session.scalar(
            query.order_by(MediaPurge.created_at).with_for_update(skip_locked=True).limit(1)
        )
        if task is None:
            return False
        try:
            purge_media(root, task.media)
        except (OSError, ValueError):
            task.attempts += 1
            task.available_at = now() + timedelta(seconds=min(86400, 60 * 2**task.attempts))
            logger.warning({"event": "account_media_cleanup_pending"})
            return False
        session.delete(task)
    return True
