import argparse
import json
import sys

from dotenv import dotenv_values

from app.components.demo.seed import seed_workspace
from app.database.session import create_engine_for, session_factory
from app.libs.config import load_settings


def main():
    parser = argparse.ArgumentParser(description="Seed Archy's original sample workspace")
    parser.add_argument("--env", required=True, help="Private configuration for the demo database")
    parser.add_argument("--confirm-demo", action="store_true")
    args = parser.parse_args()
    engine = None
    try:
        values = dotenv_values(args.env)
        if not args.confirm_demo or values.get("DEMO_ENABLED") != "true":
            raise ValueError("Explicit demo configuration is required")
        settings = load_settings(values)
        engine = create_engine_for(settings)
        with session_factory(engine)() as session:
            print(json.dumps(seed_workspace(session, settings.storage_root)))
        return 0
    except Exception:
        print(
            "Demo seed failed; check the private configuration and reserved sample data.",
            file=sys.stderr,
        )
        return 1
    finally:
        if engine:
            engine.dispose()


if __name__ == "__main__":
    sys.exit(main())
