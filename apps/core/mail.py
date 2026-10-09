"""Private local mail storage; production should use a configured SMTP backend."""

import os
import stat
from pathlib import Path

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from django.core.mail.backends.filebased import EmailBackend as DjangoFileBackend


class PrivateFileEmailBackend(DjangoFileBackend):
    def __init__(self, *args, file_path=None, **kwargs):
        directory = Path(file_path or settings.EMAIL_FILE_PATH)
        if directory.is_symlink():
            raise ImproperlyConfigured("Email directory must not be a symlink")
        directory.mkdir(mode=0o700, parents=True, exist_ok=True)
        if directory.stat().st_uid != os.getuid():
            raise ImproperlyConfigured("Email directory must belong to the current user")
        directory.chmod(0o700)
        super().__init__(*args, file_path=directory, **kwargs)

    def open(self):
        if self.stream is not None:
            return False
        descriptor = os.open(
            self._get_filename(), os.O_WRONLY | os.O_CREAT | os.O_APPEND | os.O_NOFOLLOW, 0o600
        )
        try:
            if not stat.S_ISREG(os.fstat(descriptor).st_mode):
                raise ImproperlyConfigured("Email storage must be a regular file")
            os.fchmod(descriptor, 0o600)
            self.stream = os.fdopen(descriptor, "ab")
        except Exception:
            os.close(descriptor)
            raise
        return True
