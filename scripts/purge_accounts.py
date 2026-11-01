import argparse
import os

from dotenv import dotenv_values

from app.components.preferences.purge import purge_once
from app.database.session import create_engine_for, session_factory
from app.libs.config import load_settings
from app.libs.logging import configure_logging


def main():
    parser = argparse.ArgumentParser(
        description="Retry queued private-media cleanup for closed accounts."
    )
    parser.add_argument("--env", default=".env")
    parser.add_argument("--limit", type=int, default=100)
    args = parser.parse_args()
    if not 1 <= args.limit <= 1000:
        parser.error("Limit must be between 1 and 1000.")
    settings = load_settings({**dotenv_values(args.env), **os.environ})
    configure_logging()
    engine = create_engine_for(settings, worker=True)
    cleaned = 0
    try:
        sessions = session_factory(engine)
        while cleaned < args.limit and purge_once(sessions, settings.storage_root):
            cleaned += 1
    finally:
        engine.dispose()
    print(f"Cleaned {cleaned} queued account media tasks.")


if __name__ == "__main__":
    try:
        main()
    except Exception:
        print(
            "Private media cleanup could not finish. Check private configuration and server logs."
        )
        raise SystemExit(1) from None
