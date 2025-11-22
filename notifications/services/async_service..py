# ============================================================================
# SERVICIO CON SOPORTE ASYNC
# ============================================================================

import datetime
from datetime import timezone

from notifications.dtos.notification_data import NotificationData
from notifications.tasks import send_email_notification_async, send_notification_async


class AsyncNotificationService:
    """
    Servicio wrapper para envío asíncrono de notificaciones.
    """

    @staticmethod
    def send_async(notification_data: NotificationData):
        """Envía notificación de forma asíncrona usando Celery"""
        notification_data_dict = {
            "event_code": notification_data.event_code,
            "user_id": notification_data.user_id,
            "context": notification_data.context,
            "uuid": notification_data.uuid,
            "scheduled_for": notification_data.scheduled_for.isoformat()
            if notification_data.scheduled_for
            else None,
        }

        task = send_notification_async.delay(notification_data_dict)
        return task.id

    @staticmethod
    def send_email_async(event_code: str, user_id: int, user_email: str, context: dict):
        """Envía email de forma asíncrona"""
        task = send_email_notification_async.delay(
            event_code, user_id, user_email, context
        )
        return task.id

    @staticmethod
    def schedule_notification(notification_data: NotificationData, send_at: datetime):
        """Programa una notificación para envío futuro"""
        notification_data.scheduled_for = send_at

        # Calcular countdown en segundos
        countdown = (send_at - timezone.now()).total_seconds()

        if countdown <= 0:
            # Enviar inmediatamente
            return AsyncNotificationService.send_async(notification_data)

        notification_data_dict = {
            "event_code": notification_data.event_code,
            "user_id": notification_data.user_id,
            "context": notification_data.context,
            "uuid": notification_data.uuid,
        }

        task = send_notification_async.apply_async(
            args=[notification_data_dict], countdown=countdown
        )

        return task.id
