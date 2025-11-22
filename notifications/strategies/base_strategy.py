# ============================================================================
# BASE STRATEGY - Patrón Strategy para canales
# ============================================================================

"""
base_strategy.py - Clase base abstracta para estrategias de canal.

Cada estrategia encapsula la lógica específica de un canal de notificación.
"""

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, Dict, Optional, Type

from django.template import Context, Template

from notifications.models import Notification
from notifications.providers.base import BaseProvider, ProviderResponse

logger = logging.getLogger(__name__)


@dataclass
class ChannelContent:
    """Contenido preparado para envío por un canal."""
    data: Dict[str, Any]
    recipient: str
    metadata: Optional[Dict[str, Any]] = None


class NotificationChannelStrategy(ABC):
    """
    Interfaz base para estrategias de canal.

    Cada canal debe implementar:
    - prepare_content(): Prepara el contenido desde un template
    - send(): Envía la notificación
    - get_recipient(): Obtiene el identificador del destinatario
    """

    channel_name: str = "base"
    provider_class: Optional[Type[BaseProvider]] = None

    def __init__(self, provider: Optional[BaseProvider] = None):
        """
        Inicializa la estrategia.

        Args:
            provider: Instancia del proveedor. Si es None, se crea uno nuevo.
        """
        self._provider = provider

    @property
    def provider(self) -> Optional[BaseProvider]:
        """Obtiene el proveedor, creándolo si es necesario."""
        if self._provider is None and self.provider_class:
            self._provider = self.provider_class()
        return self._provider

    @abstractmethod
    def prepare_content(self, template: Any, context: Dict[str, Any]) -> Any:
        """
        Prepara el contenido específico del canal desde un template.

        Args:
            template: Modelo de template del canal.
            context: Variables de contexto para renderizar.

        Returns:
            Objeto de contenido preparado para envío.
        """
        pass

    @abstractmethod
    def send(self, notification: Notification, content: Any) -> bool:
        """
        Envía la notificación por el canal específico.

        Args:
            notification: Modelo Notification con datos del envío.
            content: Contenido preparado por prepare_content().

        Returns:
            True si el envío fue exitoso, False en caso contrario.
        """
        pass

    def get_recipient(self, notification: Notification, context: Dict[str, Any]) -> Optional[str]:
        """
        Obtiene el identificador del destinatario para este canal.

        Args:
            notification: Modelo Notification.
            context: Contexto con datos adicionales.

        Returns:
            Identificador del destinatario (email, teléfono, token, etc.)
        """
        return notification.recipient_identifier or context.get("recipient")

    def render_template_string(self, template_string: str, context: Dict[str, Any]) -> str:
        """
        Renderiza un string de template con contexto Django.

        Args:
            template_string: String con sintaxis de template Django.
            context: Variables de contexto.

        Returns:
            String renderizado.
        """
        template = Template(template_string)
        return template.render(Context(context))

    def log_send_result(
        self,
        notification: Notification,
        success: bool,
        response: Optional[ProviderResponse] = None,
        error: Optional[str] = None
    ):
        """
        Registra el resultado del envío.

        Args:
            notification: Notificación enviada.
            success: Si fue exitoso.
            response: Respuesta del proveedor.
            error: Mensaje de error si falló.
        """
        if success:
            logger.info(
                f"[{self.channel_name}] Notificación {notification.uuid} enviada. "
                f"ID externo: {response.message_id if response else 'N/A'}"
            )
        else:
            logger.error(
                f"[{self.channel_name}] Error enviando notificación {notification.uuid}: "
                f"{error or (response.error_message if response else 'Unknown error')}"
            )

    def update_notification_from_response(
        self,
        notification: Notification,
        response: ProviderResponse
    ):
        """
        Actualiza la notificación con datos de la respuesta del proveedor.

        Args:
            notification: Notificación a actualizar.
            response: Respuesta del proveedor.
        """
        if response.message_id:
            notification.external_id = response.message_id

        if not response.success:
            notification.error_message = response.error_message
            notification.error_code = response.error_code
