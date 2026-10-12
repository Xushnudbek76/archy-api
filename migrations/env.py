from alembic import context

from app.database.base import Base
from app.database.models import register_models

MANAGED_TABLES = {model.__table__.name for model in register_models()}


def include_object(obj, name, type_, reflected, compare_to):
    return type_ != "table" or name in MANAGED_TABLES


def run_migrations(connection):
    context.configure(
        connection=connection,
        target_metadata=Base.metadata,
        version_table_schema="archy",
        include_schemas=True,
        include_object=include_object,
        compare_type=True,
        compare_server_default=True,
    )
    with context.begin_transaction():
        context.run_migrations()


connection = context.config.attributes.get("connection")
if connection is None:
    raise RuntimeError("Use the guarded migration command with explicit credentials.")
run_migrations(connection)
