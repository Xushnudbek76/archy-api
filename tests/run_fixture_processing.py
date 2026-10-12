import sys
from pathlib import Path
from uuid import UUID

from dotenv import dotenv_values

from app.components.processing.models import Job
from app.components.processing.providers import FixtureProvider
from app.components.processing.worker import run_once
from app.database.session import create_engine_for, session_factory
from app.libs.config import load_settings, validate_database_url


def main():
    root = Path(__file__).resolve().parents[1]
    values = dotenv_values(root / ".env.test")
    validate_database_url(values.get("TEST_RUNTIME_URL", ""), test=True)
    settings = load_settings(
        {
            "APP_ENV": "test",
            "SECRET_KEY": "synthetic-browser-worker-" * 4,
            "DATABASE_URL": values["TEST_RUNTIME_URL"],
            "AI_BACKEND": "fixture",
            "PROCESSING_WORKERS": "1",
            "DATABASE_CONNECTION_BUDGET": "9",
            "RECORDING_STORAGE_ROOT": str(root / ".local/recordings-test-media"),
        }
    )
    target = UUID(sys.argv[1])
    engine = create_engine_for(settings, worker=True)
    sessions = session_factory(engine)
    try:
        for _ in range(100):
            with sessions() as session:
                from sqlalchemy import select

                job = session.scalar(select(Job).where(Job.recording_id == target))
                if job is None:
                    raise ValueError("No fixture job")
                if job.stage == "COMPLETED":
                    print("Fixture recording completed.")
                    return
                if job.stage == "FAILED":
                    raise ValueError("Fixture processing failed")
            if not run_once(sessions, settings, FixtureProvider()):
                raise ValueError("Fixture work deferred")
        raise ValueError("Fixture work did not finish within its test budget")
    finally:
        engine.dispose()


if __name__ == "__main__":
    main()
