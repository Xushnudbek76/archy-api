"""Account workflows; Django owns password hashes, reset tokens and sessions."""

import logging
from smtplib import SMTPException
from urllib.parse import urlencode

from django.conf import settings
from django.contrib.auth.tokens import default_token_generator
from django.core import signing
from django.core.exceptions import ValidationError
from django.core.mail import send_mail
from django.db import IntegrityError, transaction
from django.utils import timezone
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_decode, urlsafe_base64_encode

from apps.accounts.models import User
from apps.accounts.tokens import confirmation_token, read_confirmation

logger = logging.getLogger(__name__)


class InvalidToken(ValueError):
    pass


def _send_link(email, subject, route, query):
    link = f"{settings.FRONTEND_ORIGIN}/{route}?{urlencode(query)}"
    try:
        send_mail(subject, f"{subject}\n\n{link}\n", settings.DEFAULT_FROM_EMAIL, [email])
    except (OSError, SMTPException):
        logger.error("Account email delivery failed")


def signup(email, password, display_name=""):
    try:
        with transaction.atomic():
            user = User.objects.create_user(email, password, display_name=display_name)
    except IntegrityError:
        user = User.objects.get(email__iexact=email)
    if not user.is_active and user.email_confirmed_at is None:
        _send_link(
            user.email,
            "Confirm your Archy email",
            "confirm-email",
            {"token": confirmation_token(user)},
        )


def confirm_email(token):
    try:
        data = read_confirmation(token)
        with transaction.atomic():
            user = User.objects.select_for_update().get(pk=data["uid"], email=data["email"])
            if user.is_active or user.email_confirmed_at is not None:
                raise InvalidToken
            user.is_active = True
            user.email_confirmed_at = timezone.now()
            user.save(update_fields=["is_active", "email_confirmed_at", "updated_at"])
    except (
        signing.BadSignature,
        User.DoesNotExist,
        KeyError,
        ValueError,
        ValidationError,
        TypeError,
    ):
        raise InvalidToken("Invalid confirmation") from None


def request_password_reset(email):
    user = User.objects.filter(email__iexact=email, is_active=True).first()
    if user is None or not user.has_usable_password():
        return
    _send_link(
        user.email,
        "Reset your Archy password",
        "reset-password",
        {
            "uid": urlsafe_base64_encode(force_bytes(user.pk)),
            "token": default_token_generator.make_token(user),
        },
    )


def reset_password(uid, token, password):
    try:
        identifier = urlsafe_base64_decode(uid).decode()
        with transaction.atomic():
            user = User.objects.select_for_update().get(pk=identifier, is_active=True)
            if not default_token_generator.check_token(user, token):
                raise InvalidToken
            user.set_password(password)
            user.save(update_fields=["password", "updated_at"])
    except (User.DoesNotExist, ValueError, ValidationError, UnicodeDecodeError):
        raise InvalidToken("Invalid password reset") from None
