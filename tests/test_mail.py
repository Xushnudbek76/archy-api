import os
import stat

from django.core.mail import send_mail

from config import settings as application_settings


def test_local_email_storage_is_private_even_with_permissive_umask(settings, tmp_path):
    settings.EMAIL_BACKEND = application_settings.EMAIL_BACKEND
    settings.EMAIL_FILE_PATH = tmp_path / "mail"
    previous = os.umask(0)
    try:
        send_mail("Confirmation", "test bearer", "sender@example.com", ["owner@example.com"])
    finally:
        os.umask(previous)
    assert stat.S_IMODE(settings.EMAIL_FILE_PATH.stat().st_mode) == 0o700
    assert all(
        stat.S_IMODE(path.stat().st_mode) == 0o600 for path in settings.EMAIL_FILE_PATH.iterdir()
    )


def test_existing_mail_directory_is_restricted(settings, tmp_path):
    directory = tmp_path / "mail"
    directory.mkdir(mode=0o777)
    directory.chmod(0o777)
    settings.EMAIL_BACKEND = application_settings.EMAIL_BACKEND
    settings.EMAIL_FILE_PATH = directory
    send_mail("Confirmation", "test bearer", "sender@example.com", ["owner@example.com"])
    assert stat.S_IMODE(directory.stat().st_mode) == 0o700
