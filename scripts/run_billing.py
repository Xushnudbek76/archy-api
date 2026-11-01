import os

from dotenv import dotenv_values

from app.components.billing.worker import run_due
from app.database.session import create_engine_for, session_factory
from app.libs.config import load_settings


def main():
    settings = load_settings({**dotenv_values(".env"), **os.environ})
    engine = create_engine_for(settings)
    try:
        run_due(session_factory(engine), settings.billing)
    finally:
        engine.dispose()


if __name__ == "__main__":
    main()
