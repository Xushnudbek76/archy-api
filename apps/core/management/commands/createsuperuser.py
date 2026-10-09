from django.contrib.auth.management.commands.createsuperuser import Command as DjangoCreateSuperuser


class Command(DjangoCreateSuperuser):
    # Provisioning uses normal model/password checks without privileged migration reads.
    requires_migrations_checks = False
