from django.core.management import get_commands, load_command_class


def test_runtime_development_server_skips_privileged_migration_query(monkeypatch):
    command = load_command_class(get_commands()["runserver"], "runserver")

    def forbidden(*args, **kwargs):
        raise AssertionError("Runtime must not inspect migration history")

    from django.db import connection

    monkeypatch.setattr(connection, "cursor", forbidden)
    command.check_migrations()


def test_staff_creation_does_not_require_migration_history():
    command = load_command_class(get_commands()["createsuperuser"], "createsuperuser")
    assert command.requires_migrations_checks is False
