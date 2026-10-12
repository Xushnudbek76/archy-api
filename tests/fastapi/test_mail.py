import stat
from dataclasses import replace

import pytest

from app.libs.mail import MailMessage, deliver_mail


def test_test_mail_never_uses_smtp(settings, monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("SMTP must never run in tests")

    monkeypatch.setattr("smtplib.SMTP", forbidden)
    outbox = []
    message = MailMessage(
        "synthetic@example.com", "Synthetic", "https://synthetic.example?token=synthetic"
    )
    deliver_mail(message, settings, outbox)
    assert outbox == [message]
    with pytest.raises(ValueError):
        deliver_mail(message, replace(settings, mail_backend="smtp"))


def test_file_mail_is_private(settings):
    deliver_mail(
        MailMessage("synthetic@example.com", "Synthetic", "Test"),
        replace(settings, mail_backend="file"),
    )
    assert stat.S_IMODE(settings.mail_directory.stat().st_mode) == 0o700
    files = list(settings.mail_directory.glob("*.eml"))
    assert len(files) == 1 and stat.S_IMODE(files[0].stat().st_mode) == 0o600
