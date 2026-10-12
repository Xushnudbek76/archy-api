import os
import stat
from dataclasses import replace

from app.libs.mail import MailMessage, deliver_mail


def test_local_email_storage_is_private_even_with_permissive_umask(settings):
    directory = settings.mail_directory
    directory.mkdir(mode=0o777)
    directory.chmod(0o777)
    previous = os.umask(0)
    try:
        deliver_mail(
            MailMessage("synthetic@example.com", "Confirmation", "Synthetic bearer"),
            replace(settings, mail_backend="file"),
        )
    finally:
        os.umask(previous)
    assert stat.S_IMODE(directory.stat().st_mode) == 0o700
    assert all(stat.S_IMODE(path.stat().st_mode) == 0o600 for path in directory.iterdir())
