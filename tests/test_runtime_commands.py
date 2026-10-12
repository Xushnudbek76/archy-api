import importlib.metadata
from pathlib import Path


def test_runtime_has_no_django_or_passlib():
    names = {
        distribution.metadata["Name"].lower() for distribution in importlib.metadata.distributions()
    }
    assert not {"django", "passlib", "djangorestframework", "pytest-django"} & names


def test_application_startup_does_not_run_migrations():
    source = (Path(__file__).parents[1] / "app/main.py").read_text()
    assert "alembic" not in source and "create_all" not in source
