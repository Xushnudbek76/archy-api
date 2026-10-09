import os
from pathlib import Path

from dotenv import load_dotenv

from config.environment import load_environment

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")
environment = load_environment(os.environ)
SECRET_KEY = environment.secret_key
DEBUG = False
ALLOWED_HOSTS = environment.allowed_hosts
DATABASES = {"default": environment.database}
ROOT_URLCONF = "config.urls"
WSGI_APPLICATION = "config.wsgi.application"
ASGI_APPLICATION = "config.asgi.application"
INSTALLED_APPS = [
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "django.contrib.admin",
    "rest_framework",
    "corsheaders",
    "apps.core",
]
MIDDLEWARE = [
    "apps.core.middleware.RequestMiddleware",
    "django.middleware.security.SecurityMiddleware",
    "corsheaders.middleware.CorsMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]
TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ]
        },
    }
]
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
USE_TZ = True
TIME_ZONE = "UTC"
STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / ".local" / "static"
CORS_ALLOWED_ORIGINS = [environment.frontend_origin]
CORS_ALLOW_CREDENTIALS = True
CSRF_TRUSTED_ORIGINS = [environment.frontend_origin]
CSRF_FAILURE_VIEW = "apps.core.views.csrf_failure"
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = "Lax"
CSRF_COOKIE_SAMESITE = "Lax"
SESSION_COOKIE_SECURE = environment.production
CSRF_COOKIE_SECURE = environment.production
SESSION_COOKIE_AGE = 60 * 60 * 24 * 7
SECURE_SSL_REDIRECT = environment.production
SECURE_HSTS_SECONDS = 31536000 if environment.production else 0
SECURE_HSTS_INCLUDE_SUBDOMAINS = environment.production
SECURE_HSTS_PRELOAD = environment.production
SECURE_CONTENT_TYPE_NOSNIFF = True
AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {
        "NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",
        "OPTIONS": {"min_length": 10},
    },
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]
REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": ["rest_framework.authentication.SessionAuthentication"],
    "DEFAULT_PERMISSION_CLASSES": ["rest_framework.permissions.IsAuthenticated"],
    "EXCEPTION_HANDLER": "apps.core.errors.exception_handler",
    "NUM_PROXIES": 0,
    "DEFAULT_THROTTLE_RATES": {"login": "10/min", "signup": "3/hour", "reset": "3/hour"},
}
PASSWORD_RESET_TIMEOUT = 3600
EMAIL_BACKEND = "django.core.mail.backends.filebased.EmailBackend"
EMAIL_FILE_PATH = BASE_DIR / ".local" / "mail"
DEFAULT_FROM_EMAIL = "Archy <noreply@archy.local>"
FRONTEND_ORIGIN = environment.frontend_origin
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "handlers": {"null": {"class": "logging.NullHandler"}},
    "loggers": {
        "django.request": {"handlers": ["null"], "propagate": False},
        "django.db.backends": {"handlers": ["null"], "propagate": False},
        "django.security.csrf": {"handlers": ["null"], "propagate": False},
    },
}

INSTALLED_APPS += ["apps.accounts", "apps.courses"]
AUTH_USER_MODEL = "accounts.User"
