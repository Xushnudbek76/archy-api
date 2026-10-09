import pytest

from config.environment import validate_test_url


@pytest.mark.parametrize(
    "url",
    [
        "postgresql://postgres:private@localhost/production",
        "postgresql://postgres:private@cloud.example/archy_api_test?sslmode=verify-full",
        "postgresql://postgres:private@localhost/archy_api_test?options=-c%20role=postgres",
    ],
)
def test_test_database_guard(url):
    with pytest.raises(ValueError):
        validate_test_url(url)


def test_runtime_has_dml_but_no_ddl_or_migration_history():
    import psycopg

    from conftest import fixtures
    from scripts.bootstrap_db import connection_arguments

    with psycopg.connect(
        **connection_arguments(fixtures["TEST_RUNTIME_URL"], "runtime")
    ) as connection:
        connection.execute("SELECT id FROM archy.accounts_user LIMIT 1")
        for statement in (
            "CREATE TABLE archy.forbidden(id int)",
            "SELECT * FROM archy.django_migrations",
        ):
            with pytest.raises(psycopg.errors.InsufficientPrivilege), connection.transaction():
                connection.execute(statement)
        assert connection.execute(
            "SELECT has_table_privilege(current_user, 'archy.accounts_user', 'INSERT')"
        ).fetchone()[0]
