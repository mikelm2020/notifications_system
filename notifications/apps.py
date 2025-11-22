# ============================================================================
# NOTIFICATIONS APP CONFIG
# ============================================================================

"""
apps.py - Configuración de la app Django de notificaciones.

Esta app es auto-contenida y puede copiarse a cualquier proyecto Django.
"""

from django.apps import AppConfig


class NotificationsConfig(AppConfig):
    """Configuración de la app de notificaciones."""

    default_auto_field = "django.db.models.BigAutoField"
    name = "notifications"
    verbose_name = "Sistema de Notificaciones"

    def ready(self):
        """
        Se ejecuta cuando Django carga la app.

        Conecta signals y realiza configuración inicial.
        """
        # Importar signals para conectarlos
        try:
            from notifications import signals  # noqa: F401

            # Opcionalmente conectar handlers por defecto
            # signals.notification_post_send.connect(signals.create_notification_log)
        except ImportError:
            pass

        # Registrar checks de sistema
        from django.core.checks import register, Tags
        from notifications.checks import check_notifications_config
        register(check_notifications_config, Tags.compatibility)
