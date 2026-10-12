import os
import smtplib
from dataclasses import dataclass
from email.message import EmailMessage
from uuid import uuid4

from app.libs.logging import logger


@dataclass(frozen=True)
class MailMessage:
    recipient: str
    subject: str
    body: str


def deliver_mail(message: MailMessage, settings, outbox=None):
    if settings.mail_backend == "memory":
        if outbox is None:
            raise ValueError("Memory mail requires an explicit outbox")
        outbox.append(message)
        return
    mail = EmailMessage()
    mail["From"] = settings.mail_from
    mail["To"] = message.recipient
    mail["Subject"] = message.subject
    mail.set_content(message.body)
    try:
        if settings.mail_backend == "file":
            settings.mail_directory.mkdir(mode=0o700, parents=True, exist_ok=True)
            settings.mail_directory.chmod(0o700)
            path = settings.mail_directory / f"{uuid4()}.eml"
            descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
            with os.fdopen(descriptor, "wb") as file:
                file.write(mail.as_bytes())
            return
        if settings.environment == "test":
            raise ValueError("SMTP is forbidden in tests")
        with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=10) as server:
            if settings.smtp_tls:
                server.starttls()
            if settings.smtp_username:
                server.login(settings.smtp_username, settings.smtp_password)
            server.send_message(mail)
    except (OSError, smtplib.SMTPException):
        logger.error({"event": "mail_delivery_failed"})
