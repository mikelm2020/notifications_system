# ============================================================================
# NOTIFICATIONS APP CONFIGURATION
# ============================================================================

"""
conf.py - Configuración centralizada para la app de notificaciones.

Uso en settings.py del proyecto:

NOTIFICATIONS_CONFIG = {
    "CHANNELS": {
        "email": {"enabled": True, "provider": "smtp"},
        "sms": {"enabled": True, "provider": "twilio"},
        "push": {"enabled": True, "provider": "fcm"},
        ...
    },
    "PROVIDERS": {
        "twilio": {
            "account_sid": "...",
            "auth_token": "...",
            "from_number": "+1234567890",
            "whatsapp_from": "whatsapp:+1234567890",
        },
        "fcm": {
            "credentials_path": "path/to/service-account.json",
        },
        ...
    },
    ...
}
"""

from dataclasses import dataclass, field
from typing import Any, Dict, Optional

from django.conf import settings


@dataclass
class ChannelConfig:
    """Configuración de un canal de notificación."""
    enabled: bool = True
    provider: Optional[str] = None
    options: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ProviderConfig:
    """Configuración de un proveedor externo."""
    name: str
    credentials: Dict[str, Any] = field(default_factory=dict)


# Configuración por defecto
DEFAULT_CONFIG = {
    # Canales disponibles
    "CHANNELS": {
        "email": {
            "enabled": True,
            "provider": "smtp",
            "options": {},
        },
        "in_app": {
            "enabled": True,
            "provider": None,  # No requiere provider externo
            "options": {
                "use_websocket": False,
            },
        },
        "sms": {
            "enabled": False,
            "provider": "twilio",
            "options": {},
        },
        "push_fcm": {
            "enabled": False,
            "provider": "fcm",
            "options": {},
        },
        "push_web": {
            "enabled": False,
            "provider": "webpush",
            "options": {},
        },
        "whatsapp": {
            "enabled": False,
            "provider": "twilio",
            "options": {},
        },
        "slack": {
            "enabled": False,
            "provider": "slack",
            "options": {},
        },
        "telegram": {
            "enabled": False,
            "provider": "telegram",
            "options": {},
        },
        "webhook": {
            "enabled": False,
            "provider": None,
            "options": {
                "timeout": 30,
                "verify_ssl": True,
            },
        },
    },

    # Configuración de proveedores
    "PROVIDERS": {
        "smtp": {
            # Usa la configuración de email de Django por defecto
            "use_django_settings": True,
        },
        "twilio": {
            "account_sid": "",
            "auth_token": "",
            "from_number": "",
            "whatsapp_from": "",
        },
        "fcm": {
            "credentials_path": "",
            "project_id": "",
        },
        "webpush": {
            "vapid_private_key": "",
            "vapid_public_key": "",
            "vapid_claims_email": "",
        },
        "slack": {
            "bot_token": "",
            "default_channel": "",
        },
        "telegram": {
            "bot_token": "",
        },
    },

    # Configuración general
    "DEFAULTS": {
        # Reintentos
        "max_retries": 3,
        "retry_delay": 300,  # 5 minutos

        # Rate limiting
        "rate_limit_enabled": False,
        "rate_limit_per_user": 100,  # por hora
        "rate_limit_per_channel": 1000,  # por hora

        # Batch processing
        "batch_size": 100,

        # Logging
        "log_level": "INFO",

        # Cleanup
        "cleanup_after_days": 90,
    },

    # Celery
    "CELERY": {
        "task_queue": "notifications",
        "task_priority": 5,
    },
}


class NotificationsConfig:
    """
    Clase para acceder a la configuración de notificaciones.

    Uso:
        from notifications.conf import notifications_config

        if notifications_config.is_channel_enabled("sms"):
            provider = notifications_config.get_provider_config("twilio")
    """

    _instance = None
    _config: Dict[str, Any] = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._load_config()
        return cls._instance

    def _load_config(self):
        """Carga la configuración mergeando defaults con settings del usuario."""
        user_config = getattr(settings, "NOTIFICATIONS_CONFIG", {})
        self._config = self._deep_merge(DEFAULT_CONFIG.copy(), user_config)

    def _deep_merge(self, base: Dict, override: Dict) -> Dict:
        """Merge profundo de diccionarios."""
        result = base.copy()
        for key, value in override.items():
            if key in result and isinstance(result[key], dict) and isinstance(value, dict):
                result[key] = self._deep_merge(result[key], value)
            else:
                result[key] = value
        return result

    def reload(self):
        """Recarga la configuración (útil para tests)."""
        self._load_config()

    # === Acceso a configuración ===

    def get(self, key: str, default: Any = None) -> Any:
        """Obtiene un valor de configuración por clave."""
        keys = key.split(".")
        value = self._config
        for k in keys:
            if isinstance(value, dict):
                value = value.get(k)
            else:
                return default
            if value is None:
                return default
        return value

    # === Canales ===

    def get_channel_config(self, channel_name: str) -> Optional[Dict[str, Any]]:
        """Obtiene la configuración de un canal."""
        return self._config.get("CHANNELS", {}).get(channel_name.lower())

    def is_channel_enabled(self, channel_name: str) -> bool:
        """Verifica si un canal está habilitado."""
        channel = self.get_channel_config(channel_name)
        return channel.get("enabled", False) if channel else False

    def get_enabled_channels(self) -> list:
        """Retorna lista de canales habilitados."""
        return [
            name for name, config in self._config.get("CHANNELS", {}).items()
            if config.get("enabled", False)
        ]

    # === Proveedores ===

    def get_provider_config(self, provider_name: str) -> Optional[Dict[str, Any]]:
        """Obtiene la configuración de un proveedor."""
        return self._config.get("PROVIDERS", {}).get(provider_name.lower())

    def get_provider_for_channel(self, channel_name: str) -> Optional[str]:
        """Obtiene el nombre del proveedor para un canal."""
        channel = self.get_channel_config(channel_name)
        return channel.get("provider") if channel else None

    # === Defaults ===

    @property
    def max_retries(self) -> int:
        return self._config.get("DEFAULTS", {}).get("max_retries", 3)

    @property
    def retry_delay(self) -> int:
        return self._config.get("DEFAULTS", {}).get("retry_delay", 300)

    @property
    def batch_size(self) -> int:
        return self._config.get("DEFAULTS", {}).get("batch_size", 100)

    @property
    def rate_limit_enabled(self) -> bool:
        return self._config.get("DEFAULTS", {}).get("rate_limit_enabled", False)

    @property
    def cleanup_after_days(self) -> int:
        return self._config.get("DEFAULTS", {}).get("cleanup_after_days", 90)


# Instancia global para acceso fácil
notifications_config = NotificationsConfig()
