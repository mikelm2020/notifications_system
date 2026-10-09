"""Integration tests only: isolated database on a local PostgreSQL server."""

import os

from .local import *  # noqa: F403

host = os.environ.get("NOTIFICATIONS_PG_HOST", "127.0.0.1")
if host not in {"127.0.0.1", "localhost", "::1"}:
    raise ValueError("Integration tests require a loopback PostgreSQL server")

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": "postgres",  # maintenance connection; Django creates the test DB
        "USER": os.environ.get("NOTIFICATIONS_PG_USER", "notifications_test"),
        "PASSWORD": os.environ.get("NOTIFICATIONS_PG_PASSWORD", "local-test-only"),
        "HOST": host,
        "PORT": os.environ.get("NOTIFICATIONS_PG_PORT", "55432"),
        "CONN_MAX_AGE": 0,
        "TEST": {"NAME": "test_notification_reliability"},
    }
}
