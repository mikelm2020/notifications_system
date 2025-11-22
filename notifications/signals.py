# ============================================================================
# NOTIFICATIONS SIGNALS
# ============================================================================

"""
signals.py - Signals para integración y hooks de notificaciones.

Estos signals permiten que otras apps reaccionen a eventos del sistema
de notificaciones sin acoplamiento directo.
"""

from django.dispatch import Signal

# === Signals de Notificación ===

# Disparado antes de crear una notificación
# sender: NotificationService
# notification_data: NotificationData
notification_pre_create = Signal()

# Disparado después de crear una notificación
# sender: NotificationService
# notification: Notification
# notification_data: NotificationData
notification_post_create = Signal()

# Disparado antes de enviar una notificación
# sender: NotificationChannelStrategy
# notification: Notification
# content: ChannelContent
notification_pre_send = Signal()

# Disparado después de enviar una notificación (exitoso o no)
# sender: NotificationChannelStrategy
# notification: Notification
# success: bool
# response: ProviderResponse (opcional)
notification_post_send = Signal()

# Disparado cuando una notificación es marcada como leída
# sender: Notification
# user: User
notification_read = Signal()

# Disparado cuando una notificación falla después de todos los reintentos
# sender: NotificationService
# notification: Notification
# error: Exception
notification_failed_permanently = Signal()


# === Signals de Dispositivo ===

# Disparado cuando se registra un nuevo dispositivo
# sender: DeviceToken
# user: User
# platform: str
device_registered = Signal()

# Disparado cuando un dispositivo es desactivado
# sender: DeviceToken
# user: User
# reason: str (expired, invalid, manual)
device_deactivated = Signal()


# === Signals de Preferencias ===

# Disparado cuando un usuario cambia sus preferencias
# sender: UserNotificationPreference
# user: User
# channel: str
# is_enabled: bool
preference_changed = Signal()


# === Handlers de ejemplo ===

def log_notification_sent(sender, notification, success, **kwargs):
    """
    Handler de ejemplo que loguea notificaciones enviadas.

    Uso:
        notification_post_send.connect(log_notification_sent)
    """
    import logging
    logger = logging.getLogger("notifications")

    if success:
        logger.info(
            f"Notificación {notification.uuid} enviada por {notification.channel_id.name}"
        )
    else:
        logger.warning(
            f"Notificación {notification.uuid} falló: {notification.error_message}"
        )


def create_notification_log(sender, notification, success, **kwargs):
    """
    Handler que crea un registro en NotificationLog.

    Uso:
        notification_post_send.connect(create_notification_log)
    """
    from notifications.models import NotificationLog

    NotificationLog.objects.create(
        notification=notification,
        action="sent" if success else "failed",
        details={
            "channel": notification.channel_id.name,
            "external_id": notification.external_id,
        },
        error_message=notification.error_message if not success else "",
    )


def notify_admin_on_permanent_failure(sender, notification, error, **kwargs):
    """
    Handler que notifica a admins cuando una notificación falla permanentemente.

    Uso:
        notification_failed_permanently.connect(notify_admin_on_permanent_failure)
    """
    import logging
    logger = logging.getLogger("notifications")

    logger.error(
        f"Notificación {notification.uuid} falló permanentemente después de "
        f"{notification.retry_count} intentos: {error}"
    )
    # Aquí podrías enviar un email a admins, crear un ticket, etc.
