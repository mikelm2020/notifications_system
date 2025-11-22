# ============================================================================
# IN-APP STRATEGY
# ============================================================================

"""
inapp_strategy.py - Estrategia para notificaciones In-App.

Las notificaciones in-app se almacenan en base de datos y
opcionalmente se envían via WebSocket para tiempo real.
"""

import logging
from dataclasses import dataclass
from typing import Any, Dict, Optional

from notifications.models import InAppTemplate, Notification
from notifications.strategies.base_strategy import NotificationChannelStrategy

logger = logging.getLogger(__name__)


@dataclass
class InAppContent:
    """Contenido para notificación in-app."""
    title: str
    message: str
    icon: Optional[str] = None
    action_url: Optional[str] = None
    action_label: Optional[str] = None
    data: Optional[Dict[str, Any]] = None


class InAppChannelStrategy(NotificationChannelStrategy):
    """
    Estrategia para canal In-App.

    Las notificaciones in-app se guardan en BD y están disponibles
    para consulta via API. Opcionalmente pueden enviarse en tiempo
    real via WebSocket si Django Channels está configurado.
    """

    channel_name = "in_app"
    provider_class = None  # No requiere provider externo

    def __init__(self, use_websocket: bool = False):
        super().__init__(None)
        self.use_websocket = use_websocket

    def prepare_content(
        self,
        template: InAppTemplate,
        context: Dict[str, Any]
    ) -> InAppContent:
        """
        Prepara el contenido in-app.

        Args:
            template: Modelo InAppTemplate.
            context: Variables de contexto.

        Returns:
            InAppContent con título, mensaje, etc.
        """
        title = self.render_template_string(template.title, context)
        message = self.render_template_string(template.message, context)

        action_url = None
        if template.action_url:
            action_url = self.render_template_string(template.action_url, context)

        return InAppContent(
            title=title,
            message=message,
            icon=template.icon or None,
            action_url=action_url,
            action_label=template.action_label or None,
            data=context.get("data"),
        )

    def send(self, notification: Notification, content: InAppContent) -> bool:
        """
        "Envía" la notificación in-app.

        En realidad, la notificación ya está guardada en BD.
        Este método opcionalmente la envía via WebSocket.

        Args:
            notification: Modelo Notification.
            content: InAppContent preparado.

        Returns:
            True (siempre exitoso ya que está en BD).
        """
        try:
            # Guardar contenido renderizado
            notification.rendered_content = {
                "title": content.title,
                "message": content.message,
                "icon": content.icon,
                "action_url": content.action_url,
                "action_label": content.action_label,
            }

            # Enviar via WebSocket si está habilitado
            if self.use_websocket:
                self._send_websocket(notification, content)

            logger.info(f"Notificación in-app creada: {notification.uuid}")
            return True

        except Exception as e:
            logger.error(f"Error procesando notificación in-app {notification.uuid}: {str(e)}")
            return True  # Aún así retornamos True porque está en BD

    def _send_websocket(self, notification: Notification, content: InAppContent):
        """
        Envía la notificación via WebSocket usando Django Channels.

        Requiere Django Channels configurado con un consumer apropiado.
        """
        try:
            from asgiref.sync import async_to_sync
            from channels.layers import get_channel_layer

            channel_layer = get_channel_layer()
            if channel_layer is None:
                logger.warning("Channel layer no configurado para WebSocket")
                return

            user_id = notification.user_id.id if notification.user_id else None
            if not user_id:
                return

            # Nombre del grupo del usuario
            group_name = f"notifications_{user_id}"

            # Enviar mensaje al grupo
            async_to_sync(channel_layer.group_send)(
                group_name,
                {
                    "type": "notification.message",
                    "notification": {
                        "uuid": str(notification.uuid),
                        "title": content.title,
                        "message": content.message,
                        "icon": content.icon,
                        "action_url": content.action_url,
                        "action_label": content.action_label,
                        "created_at": notification.created_at.isoformat(),
                        "type": notification.notification_type_id.event_code,
                    }
                }
            )

            logger.debug(f"WebSocket enviado para notificación {notification.uuid}")

        except ImportError:
            logger.debug("Django Channels no está instalado, omitiendo WebSocket")
        except Exception as e:
            logger.warning(f"Error enviando WebSocket: {str(e)}")
