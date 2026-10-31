import os
from pathlib import Path

from dotenv import dotenv_values

from app.libs.config import load_settings, validate_database_url
from app.main import create_app


def test_app():
    root = Path(__file__).resolve().parents[1]
    values = dotenv_values(root / ".env.test")
    validate_database_url(values.get("TEST_RUNTIME_URL", ""), test=True)
    port = int(os.environ.get("TEST_API_PORT", "3137"))
    if not 1024 <= port <= 65535:
        raise ValueError("Invalid test port")
    settings = load_settings(
        {
            "APP_ENV": "test",
            "SECRET_KEY": "synthetic-test-api-secret-" * 4,
            "DATABASE_URL": values["TEST_RUNTIME_URL"],
            "FRONTEND_ORIGIN": os.environ.get("TEST_FRONTEND_ORIGIN", "http://127.0.0.1:3130"),
            "RECORDING_STORAGE_ROOT": str(root / ".local/recordings-test-media"),
            "MAIL_DIRECTORY": str(root / ".local/recordings-test-mail"),
            "MAIL_BACKEND": "file",
            "DEMO_ENABLED": os.environ.get("TEST_DEMO_ENABLED", "false"),
        }
    )
    if not settings.frontend_origin.startswith(("http://127.0.0.1:", "http://localhost:")):
        raise ValueError("Test frontend must be loopback")
    app = create_app(settings)
    if settings.demo_enabled:
        from app.components.demo.seed import seed_workspace

        with app.state.sessions() as session:
            seed_workspace(session, settings.storage_root)
    # Browser scenarios need independent accounts; account limit behavior has dedicated tests.
    from app.libs.throttling import LIMITS

    LIMITS.update(login=(1000, 60), signup=(1000, 3600), reset=(1000, 3600))
    return app


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        test_app(),
        host="127.0.0.1",
        port=int(os.environ.get("TEST_API_PORT", "3137")),
        access_log=False,
    )
