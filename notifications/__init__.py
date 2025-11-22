# ============================================================================
# DJANGO NOTIFICATIONS SYSTEM
# ============================================================================

"""
notifications - Sistema de notificaciones multi-canal para Django.

Canales soportados:
    - Email (SMTP)
    - In-App (con soporte opcional para WebSocket)
    - SMS (Twilio)
    - Push FCM (Firebase Cloud Messaging)
    - Push Web (Web Push API)
    - WhatsApp (Twilio)
    - Slack
    - Telegram
    - Webhook

Uso básico:
    from notifications import send_notification

    send_notification(
        event_code="ORDER_CREATED",
        user_id=user.id,
        context={"order_number": "12345"},
    )

Uso con Celery:
    from notifications import send_notification_async

    send_notification_async.delay({
        "event_code": "ORDER_CREATED",
        "user_id": user.id,
        "context": {"order_number": "12345"},
    })
"""

__version__ = "1.0.0"
__author__ = "Miguel Angel López Monroy"

# API pública
from notifications.conf import notifications_config
from notifications.dtos.notification_data import NotificationData
from notifications.services.notification_service import NotificationService


def send_notification(
    event_code: str,
    user_id: int = None,
    context: dict = None,
    channels: list = None,
    scheduled_for=None,
):
    """
    Envía una notificación de forma síncrona.

    Args:
        event_code: Código del tipo de notificación (ej: "ORDER_CREATED").
        user_id: ID del usuario destinatario (opcional).
        context: Variables de contexto para los templates.
        channels: Lista de canales específicos (opcional, usa todos si es None).
        scheduled_for: Datetime para envío programado (opcional).

    Returns:
        Lista de objetos Notification creados.

    Example:
        notifications = send_notification(
            event_code="PASSWORD_RESET",
            user_id=user.id,
            context={"reset_link": "https://..."},
            channels=["email"],
        )
    """
    notification_data = NotificationData(
        event_code=event_code,
        user_id=user_id,
        context=context or {},
        scheduled_for=scheduled_for,
    )

    service = NotificationService()
    return service.create_and_send_notification(notification_data, channels=channels)


# Exponer tarea de Celery para uso directo
try:
    from notifications.tasks import send_notification_async
except ImportError:
    send_notification_async = None


__all__ = [
    # Configuración
    "notifications_config",
    # DTOs
    "NotificationData",
    # Servicios
    "NotificationService",
    # Funciones de conveniencia
    "send_notification",
    "send_notification_async",
    # Versión
    "__version__",
]
