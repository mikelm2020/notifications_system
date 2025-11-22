# ============================================================================
# CELERY CONFIGURATION
# ============================================================================

"""
celery.py - Configuración de Celery
"""

import os

from celery import Celery
from celery.schedules import crontab

os.setenv("DJANGO_SETTINGS_MODULE", "notifications_system.settings")

app = Celery("your_project")
app.config_from_object("django.conf:settings", namespace="CELERY")
app.autodiscover_tasks()

# Configuración de tareas periódicas
app.conf.beat_schedule = {
    "retry-failed-notifications": {
        "task": "notifications.tasks.retry_failed_notifications",
        "schedule": crontab(minute="*/15"),  # Cada 15 minutos
    },
    "process-scheduled-notifications": {
        "task": "notifications.tasks.process_scheduled_notifications",
        "schedule": crontab(minute="*"),  # Cada minuto
    },
}
