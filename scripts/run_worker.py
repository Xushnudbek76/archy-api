import fcntl
import logging
import os
import shutil
import signal
import threading
import time

from dotenv import dotenv_values
from sqlalchemy import select

from app.components.processing.models import Job, now
from app.components.processing.providers import FixtureProvider, GroqProvider
from app.components.processing.worker import run_once
from app.database.session import create_engine_for, session_factory
from app.libs.config import load_settings
from app.libs.logging import configure_logging


def cleanup(sessions, root):
    if not root.exists():
        return
    with sessions() as session:
        active = {
            f"{j.id}-{j.lease_token}-"
            for j in session.scalars(select(Job).where(Job.lease_expires_at > now()))
        }
    for directory in root.iterdir():
        if directory.is_dir() and not any(directory.name.startswith(prefix) for prefix in active):
            shutil.rmtree(directory)


def main():
    settings = load_settings({**dotenv_values(".env"), **os.environ})
    if settings.processing.workers != 1 or settings.processing.backend == "disabled":
        raise ValueError("Enable one processing worker and configure its provider")
    provider = (
        GroqProvider(settings.processing.api_key)
        if settings.processing.backend == "groq"
        else FixtureProvider()
    )
    configure_logging()
    logging.getLogger("httpx").setLevel(logging.WARNING)
    engine = create_engine_for(settings, worker=True)
    sessions = session_factory(engine)
    settings.storage_root.mkdir(parents=True, exist_ok=True, mode=0o700)
    stopped = threading.Event()
    for signum in (signal.SIGTERM, signal.SIGINT):
        signal.signal(signum, lambda *_: stopped.set())
    try:
        with (settings.storage_root / ".processing-worker.lock").open("a") as lock:
            os.chmod(lock.name, 0o600)
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            cleanup(sessions, settings.storage_root / "processing")
            last_cleanup = time.monotonic()
            while not stopped.is_set():
                try:
                    worked = run_once(sessions, settings, provider)
                    if worked or time.monotonic() - last_cleanup >= 30:
                        cleanup(sessions, settings.storage_root / "processing")
                        last_cleanup = time.monotonic()
                except Exception:
                    logging.getLogger("archy").warning({"event": "processing_database_unavailable"})
                    worked = False
                stopped.wait(0.2 if worked else 2)
    finally:
        engine.dispose()


if __name__ == "__main__":
    try:
        main()
    except Exception:
        print(
            "Worker could not start. Check private configuration, migration and worker ownership."
        )
        raise SystemExit(1) from None
