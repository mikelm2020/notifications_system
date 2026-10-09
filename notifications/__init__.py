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
    from notifications.dtos.notification_data import NotificationData
    from notifications.services.notification_service import NotificationService

    notification_data = NotificationData(
        event_code=event_code,
        user_id=user_id,
        context=context or {},
        scheduled_for=scheduled_for,
    )

    service = NotificationService()
    return service.create_and_send_notification(notification_data, channels=channels)


def __getattr__(name):
    # Django imports the package before its app registry is ready.
    from importlib import import_module

    exports = {
        "notifications_config": "notifications.conf",
        "NotificationData": "notifications.dtos.notification_data",
        "NotificationService": "notifications.services.notification_service",
        "send_notification_async": "notifications.tasks",
    }
    if name in exports:
        return getattr(import_module(exports[name]), name)
    raise AttributeError(name)


__all__ = [
    "notifications_config",
    "NotificationData",
    "NotificationService",
    "send_notification",
    "send_notification_async",
    "__version__",
]
