import pytest

from app.libs.config import load_settings, validate_database_url

URL = "postgresql://archy_api_runtime:private@localhost:55433/archy_api_test"


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
    with pytest.raises(ValueError) as error:
        validate_database_url(url)
    assert "private" not in str(error.value)


def test_environment_requires_credentials():
    data = {"SECRET_KEY": "x" * 64, "DATABASE_URL": URL}
    for key in data:
        with pytest.raises(ValueError):
            load_settings({name: value for name, value in data.items() if name != key})
