# ============================================================================
# FACTORY - Patrón Factory para crear estrategias
# ============================================================================

"""
channel_factory.py - Factory para crear estrategias de canal.

Implementa el patrón Factory para instanciar la estrategia correcta
basándose en el nombre del canal.
"""

from typing import Dict, Optional, Type

from notifications.conf import notifications_config
from notifications.exceptions import ChannelNotEnabledError, ChannelNotFoundError
from notifications.strategies.base_strategy import NotificationChannelStrategy


class NotificationChannelFactory:
    """
    Factory para crear estrategias de canal de notificación.

    Uso:
        strategy = NotificationChannelFactory.create("email")
        content = strategy.prepare_content(template, context)
        success = strategy.send(notification, content)
    """

    _strategies: Dict[str, Type[NotificationChannelStrategy]] = {}
    _initialized: bool = False

    @classmethod
    def _initialize(cls):
        """Inicializa las estrategias disponibles."""
        if cls._initialized:
            return

        # Importar estrategias aquí para evitar imports circulares
        from notifications.strategies.email_strategy import EmailChannelStrategy
        from notifications.strategies.inapp_strategy import InAppChannelStrategy
        from notifications.strategies.sms_strategy import SMSChannelStrategy
        from notifications.strategies.push_fcm_strategy import PushFCMChannelStrategy
        from notifications.strategies.push_web_strategy import PushWebChannelStrategy
        from notifications.strategies.whatsapp_strategy import WhatsAppChannelStrategy
        from notifications.strategies.slack_strategy import SlackChannelStrategy
        from notifications.strategies.telegram_strategy import TelegramChannelStrategy
        from notifications.strategies.webhook_strategy import WebhookChannelStrategy

        cls._strategies = {
            "email": EmailChannelStrategy,
            "in_app": InAppChannelStrategy,
            "sms": SMSChannelStrategy,
            "push_fcm": PushFCMChannelStrategy,
            "push_web": PushWebChannelStrategy,
            "whatsapp": WhatsAppChannelStrategy,
            "slack": SlackChannelStrategy,
            "telegram": TelegramChannelStrategy,
            "webhook": WebhookChannelStrategy,
        }

        cls._initialized = True

    @classmethod
    def create(
        cls,
        channel_name: str,
        check_enabled: bool = True,
        **kwargs
    ) -> NotificationChannelStrategy:
        """
        Crea una instancia de estrategia basada en el nombre del canal.

        Args:
            channel_name: Nombre del canal (email, sms, push_fcm, etc.)
            check_enabled: Si True, verifica que el canal esté habilitado
                          en NOTIFICATIONS_CONFIG.
            **kwargs: Argumentos adicionales para el constructor de la estrategia.

        Returns:
            Instancia de NotificationChannelStrategy.

        Raises:
            ChannelNotFoundError: Si el canal no existe.
            ChannelNotEnabledError: Si el canal no está habilitado.
        """
        cls._initialize()

        channel_name_lower = channel_name.lower()
        strategy_class = cls._strategies.get(channel_name_lower)

        if not strategy_class:
            raise ChannelNotFoundError(channel_name)

        if check_enabled and not notifications_config.is_channel_enabled(channel_name_lower):
            raise ChannelNotEnabledError(channel_name)

        return strategy_class(**kwargs)

    @classmethod
    def register_strategy(
        cls,
        channel_name: str,
        strategy_class: Type[NotificationChannelStrategy]
    ):
        """
        Registra una nueva estrategia de canal.

        Útil para agregar canales personalizados sin modificar el código fuente.

        Args:
            channel_name: Nombre único del canal.
            strategy_class: Clase que hereda de NotificationChannelStrategy.

        Example:
            class CustomChannelStrategy(NotificationChannelStrategy):
                ...

            NotificationChannelFactory.register_strategy("custom", CustomChannelStrategy)
        """
        cls._initialize()
        cls._strategies[channel_name.lower()] = strategy_class

    @classmethod
    def unregister_strategy(cls, channel_name: str):
        """
        Elimina una estrategia registrada.

        Args:
            channel_name: Nombre del canal a eliminar.
        """
        cls._strategies.pop(channel_name.lower(), None)

    @classmethod
    def get_available_channels(cls) -> list:
        """
        Retorna lista de canales disponibles (registrados).

        Returns:
            Lista de nombres de canales.
        """
        cls._initialize()
        return list(cls._strategies.keys())

    @classmethod
    def get_enabled_channels(cls) -> list:
        """
        Retorna lista de canales habilitados en la configuración.

        Returns:
            Lista de nombres de canales habilitados.
        """
        cls._initialize()
        return [
            name for name in cls._strategies.keys()
            if notifications_config.is_channel_enabled(name)
        ]

    @classmethod
    def is_channel_available(cls, channel_name: str) -> bool:
        """
        Verifica si un canal está disponible (registrado).

        Args:
            channel_name: Nombre del canal.

        Returns:
            True si el canal está registrado.
        """
        cls._initialize()
        return channel_name.lower() in cls._strategies

    @classmethod
    def is_channel_enabled(cls, channel_name: str) -> bool:
        """
        Verifica si un canal está habilitado.

        Args:
            channel_name: Nombre del canal.

        Returns:
            True si el canal está registrado Y habilitado.
        """
        cls._initialize()
        return (
            cls.is_channel_available(channel_name) and
            notifications_config.is_channel_enabled(channel_name.lower())
        )
