import pytest

from config.environment import database_configuration, load_environment

URL = "postgresql://archy_api_runtime:private@localhost:55433/archy_api_test"


def values(**extra):
    return {"DJANGO_SECRET_KEY": "x" * 64, "DATABASE_URL": URL, **extra}


def test_environment_requires_credentials():
    for missing in ("DJANGO_SECRET_KEY", "DATABASE_URL"):
        data = values()
        del data[missing]
        with pytest.raises(ValueError):
            load_environment(data)


@pytest.mark.parametrize(
    "url",
    [
        URL.replace("archy_api_runtime", "postgres"),
        URL + "?options=-c%20search_path=public",
        URL + "?user=postgres",
        URL + "?sslmode=disable&sslmode=require",
        URL + "#fragment",
        URL.replace("localhost", "pooler.supabase.com"),
        URL.replace("private@", "@"),
    ],
)
def test_rejects_unsafe_database_urls_without_leaking_password(url):
    with pytest.raises(ValueError) as caught:
        database_configuration(url, "runtime")
    assert "private" not in str(caught.value)
    assert url not in str(caught.value)


def test_runtime_database_options_are_owned_by_server():
    db = database_configuration(URL, "runtime")
    assert db["USER"] == "archy_api_runtime"
    assert db["OPTIONS"]["connect_timeout"] == 5
    assert "search_path=archy" in db["OPTIONS"]["options"]
    assert "statement_timeout=5000" in db["OPTIONS"]["options"]


def test_production_requires_https_origin_and_explicit_hosts():
    with pytest.raises(ValueError):
        load_environment(values(DJANGO_ENV="production"))
    env = load_environment(
        values(
            DJANGO_ENV="production",
            ALLOWED_HOSTS="api.archy.example",
            FRONTEND_ORIGIN="https://archy.example",
        )
    )
    assert env.production
