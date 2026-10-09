from django.contrib.auth.base_user import BaseUserManager


class UserManager(BaseUserManager):
    use_in_migrations = True

    def get_by_natural_key(self, email):
        return self.get(email__iexact=email.strip())

    def create_user(self, email, password=None, **extra_fields):
        if not email:
            raise ValueError("Email required")
        user = self.model(email=email.strip().lower(), **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(self, email, password, **extra_fields):
        for flag in ("is_staff", "is_superuser", "is_active"):
            extra_fields.setdefault(flag, True)
            if extra_fields[flag] is not True:
                raise ValueError("Administrator flags must be enabled")
        return self.create_user(email, password, **extra_fields)
