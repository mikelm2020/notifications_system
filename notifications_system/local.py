"""Entorno local y de pruebas sin servicios ni credenciales externos."""
from .settings import *  # noqa: F403

SECRET_KEY = "local-development-only"
INSTALLED_APPS = [*INSTALLED_APPS, "notifications.apps.NotificationsConfig"]  # noqa: F405
EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"
EMAIL_HOST_USER = ""
EMAIL_HOST_PASSWORD = ""
CELERY_BROKER_URL = "memory://"
CELERY_RESULT_BACKEND = "cache+memory://"
CELERY_TASK_ALWAYS_EAGER = True
CELERY_TASK_EAGER_PROPAGATES = True
