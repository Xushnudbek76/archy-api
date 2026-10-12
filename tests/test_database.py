import pytest
from sqlalchemy import text
from sqlalchemy.exc import ProgrammingError

from app.database.session import create_engine_for


def test_runtime_role_cannot_migrate_and_history_has_no_grants(settings, prepared_database):
    engine = create_engine_for(settings)
    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT id FROM archy.accounts_user LIMIT 1"))
            for statement in [
                "CREATE TABLE archy.forbidden(id int)",
                "SELECT * FROM archy.alembic_version",
                "SELECT * FROM archy.django_migrations",
                "SELECT * FROM archy.django_session",
            ]:
                with pytest.raises(ProgrammingError), connection.begin_nested():
                    connection.execute(text(statement))
            assert connection.execute(
                text("SELECT has_table_privilege(current_user,'archy.accounts_user','INSERT')")
            ).scalar_one()
    finally:
        engine.dispose()
