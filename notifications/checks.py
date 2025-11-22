# ============================================================================
# SYSTEM CHECKS
# ============================================================================

"""
checks.py - System checks para validar la configuración de la app.
"""

from django.core.checks import Error, Warning


def check_notifications_config(app_configs, **kwargs):
    """
    Verifica que la configuración de notificaciones sea válida.

    Ejecutado por Django al iniciar con `python manage.py check`.
    """
    errors = []

    try:
        from notifications.conf import notifications_config

        # Verificar canales habilitados tienen providers configurados
        enabled_channels = notifications_config.get_enabled_channels()

        for channel in enabled_channels:
            channel_config = notifications_config.get_channel_config(channel)
            provider_name = channel_config.get("provider")

            if provider_name:
                provider_config = notifications_config.get_provider_config(provider_name)

                if not provider_config:
                    errors.append(
                        Warning(
                            f"Canal '{channel}' está habilitado pero el proveedor "
                            f"'{provider_name}' no está configurado.",
                            hint=f"Agrega configuración para '{provider_name}' en "
                                 "NOTIFICATIONS_CONFIG['PROVIDERS']",
                            id="notifications.W001",
                        )
                    )

        # Verificar dependencias opcionales para canales habilitados
        channel_dependencies = {
            "sms": ("twilio", "pip install twilio"),
            "whatsapp": ("twilio", "pip install twilio"),
            "push_fcm": ("firebase_admin", "pip install firebase-admin"),
            "push_web": ("pywebpush", "pip install pywebpush"),
            "slack": ("slack_sdk", "pip install slack-sdk"),
            "telegram": ("httpx", "pip install httpx"),
            "webhook": ("httpx", "pip install httpx"),
        }

        for channel, (module, install_cmd) in channel_dependencies.items():
            if channel in enabled_channels:
                try:
                    __import__(module)
                except ImportError:
                    errors.append(
                        Warning(
                            f"Canal '{channel}' está habilitado pero falta la dependencia '{module}'.",
                            hint=f"Instala con: {install_cmd}",
                            id="notifications.W002",
                        )
                    )

    except Exception as e:
        errors.append(
            Error(
                f"Error al verificar configuración de notificaciones: {e}",
                id="notifications.E001",
            )
        )

    return errors
