from django.contrib.staticfiles.management.commands.runserver import Command as DjangoRunserver


class Command(DjangoRunserver):
    def check_migrations(self):
        # Migration verification belongs to scripts.migrate_db, not the runtime role.
        return None
