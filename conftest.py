import os

os.environ["DJANGO_SETTINGS_MODULE"] = "config.settings"
os.environ["DJANGO_SECRET_KEY"] = "isolated-test-secret-" * 4
os.environ["DJANGO_ENV"] = "test"
os.environ["DATABASE_URL"] = "postgresql://archy_api_runtime:private@localhost:55433/archy_api_test"
os.environ["DATABASE_ROLE"] = "runtime"

import django

django.setup()
