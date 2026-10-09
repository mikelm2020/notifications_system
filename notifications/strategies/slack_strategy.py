# ============================================================================
# SLACK STRATEGY
# ============================================================================

"""
slack_strategy.py - Estrategia para notificaciones Slack.
"""

import json
import logging
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from notifications.models import Notification, SlackTemplate
from notifications.providers.slack_provider import SlackProvider
from notifications.strategies.base_strategy import NotificationChannelStrategy

logger = logging.getLogger(__name__)


@dataclass
class SlackContent:
    """Contenido para notificación Slack."""

    message: str
    channel: str
    blocks: Optional[List[Dict]] = None
    thread_ts: Optional[str] = None


class SlackChannelStrategy(NotificationChannelStrategy):
    """Estrategia para canal Slack."""

    channel_name = "slack"
    provider_class = SlackProvider

    def prepare_content(self, template: SlackTemplate, context: Dict[str, Any]) -> SlackContent:
        """
        Prepara el contenido de Slack.

        Args:
            template: Modelo SlackTemplate.
            context: Variables de contexto.

        Returns:
            SlackContent con mensaje y blocks.
        """
        message = self.render_template_string(template.message, context)

        # Procesar blocks si existen
        blocks = None
        if template.blocks:
            # Renderizar variables en los blocks
            blocks_str = json.dumps(template.blocks)
            blocks_str = self.render_template_string(blocks_str, context)
            blocks = json.loads(blocks_str)

        # Determinar canal
        channel = template.channel_override or context.get("slack_channel", "")

        return SlackContent(
            message=message,
            channel=channel,
            blocks=blocks,
            thread_ts=context.get("thread_ts"),
        )

    def get_recipient(self, notification: Notification, context: Dict[str, Any]) -> Optional[str]:
        """Obtiene el ID de Slack del destinatario."""
        if notification.recipient_identifier:
            return notification.recipient_identifier

        if context.get("slack_user_id"):
            return context["slack_user_id"]

        if context.get("slack_channel"):
            return context["slack_channel"]

        # Buscar en cuentas externas del usuario
        if notification.user_id:
            try:
                from notifications.models import UserExternalAccount

                account = UserExternalAccount.objects.filter(
                    user=notification.user_id,
                    account_type="slack",
                    is_verified=True,
                ).first()
                if account and account.external_id:
                    return account.external_id
            except Exception:
                pass

        return None

    def send(self, notification: Notification, content: SlackContent) -> bool:
        """
        Envía el mensaje a Slack.

        Args:
            notification: Modelo Notification.
            content: SlackContent preparado.

        Returns:
            True si el envío fue exitoso.
        """
        try:
            provider = self.provider

            # Determinar destinatario
            recipient = content.channel or self.get_recipient(
                notification, notification.context_data or {}
            )

            if not recipient:
                # Usar canal por defecto de la configuración
                from notifications.conf import notifications_config

                provider_config = notifications_config.get_provider_config("slack")
                recipient = provider_config.get("default_channel") if provider_config else None

            if not recipient:
                logger.error(f"No hay canal/usuario Slack para notificación {notification.uuid}")
                notification.error_message = "No hay destinatario Slack configurado"
                return False

            # Determinar si es un usuario o canal
            if recipient.startswith("U"):
                # Es un usuario, enviar DM
                response = provider.send_direct_message(
                    user_id=recipient,
                    content={
                        "text": content.message,
                        "blocks": content.blocks,
                    },
                    thread_ts=content.thread_ts,
                )
            else:
                # Es un canal
                response = provider.send(
                    recipient=recipient,
                    content={
                        "text": content.message,
                        "blocks": content.blocks,
                    },
                    thread_ts=content.thread_ts,
                )

            self.update_notification_from_response(notification, response)
            self.log_send_result(notification, response.success, response)

            # Guardar contenido renderizado
            notification.rendered_content = {
                "message": content.message,
                "channel": recipient,
                "has_blocks": bool(content.blocks),
            }
            notification.recipient_identifier = recipient

            return response.success

        except Exception as e:
            logger.error(f"Error enviando a Slack {notification.uuid}: {str(e)}")
            self.record_send_error(notification, e)
            return False
