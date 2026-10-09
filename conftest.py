import os

import django
import pytest
from dotenv import dotenv_values

from config.environment import database_configuration, validate_test_url

fixtures = {**dotenv_values(".env.test"), **os.environ}
validate_test_url(fixtures.get("TEST_DATABASE_URL", ""))
for key, role in (("TEST_MIGRATION_URL", "migration"), ("TEST_RUNTIME_URL", "runtime")):
    database_configuration(fixtures.get(key, ""), role)
    from urllib.parse import urlsplit

    target = urlsplit(fixtures[key])
    if target.hostname not in {"localhost", "127.0.0.1", "::1"} or target.path != "/archy_api_test":
        raise ValueError("All test connections must be loopback archy_api_test")

os.environ["DJANGO_SETTINGS_MODULE"] = "config.settings"
os.environ["DJANGO_SECRET_KEY"] = "isolated-test-secret-" * 4
os.environ["DJANGO_ENV"] = "test"
os.environ["DATABASE_URL"] = fixtures["TEST_MIGRATION_URL"]
os.environ["DATABASE_ROLE"] = "migration"
os.environ["ALLOWED_HOSTS"] = "localhost,127.0.0.1,testserver"
django.setup()


@pytest.fixture(scope="session")
def django_db_setup():
    """Use only the pre-created, migrated disposable database; never create hosted DBs."""
    pass


@pytest.fixture(autouse=True)
def clear_throttle_cache():
    from django.core.cache import cache

    cache.clear()
