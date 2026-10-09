from django.core import signing

CONFIRMATION_SALT = "archy.accounts.confirm-email"
CONFIRMATION_MAX_AGE = 24 * 60 * 60


def confirmation_token(user):
    return signing.dumps({"uid": str(user.pk), "email": user.email}, salt=CONFIRMATION_SALT)


def read_confirmation(token):
    return signing.loads(token, salt=CONFIRMATION_SALT, max_age=CONFIRMATION_MAX_AGE)
