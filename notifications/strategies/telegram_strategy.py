# ============================================================================
# TELEGRAM STRATEGY
# ============================================================================

"""
telegram_strategy.py - Estrategia para notificaciones Telegram.
"""

import json
import logging
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from notifications.models import Notification, TelegramTemplate
from notifications.providers.telegram_provider import TelegramProvider
from notifications.strategies.base_strategy import NotificationChannelStrategy

logger = logging.getLogger(__name__)


@dataclass
class TelegramContent:
    """Contenido para notificación Telegram."""
    message: str
    parse_mode: str = "HTML"
    disable_preview: bool = False
    buttons: Optional[List[List[Dict]]] = None


class TelegramChannelStrategy(NotificationChannelStrategy):
    """Estrategia para canal Telegram."""

    channel_name = "telegram"
    provider_class = TelegramProvider

    def prepare_content(
        self,
        template: TelegramTemplate,
        context: Dict[str, Any]
    ) -> TelegramContent:
        """
        Prepara el contenido de Telegram.

        Args:
            template: Modelo TelegramTemplate.
            context: Variables de contexto.

        Returns:
            TelegramContent con mensaje y configuración.
        """
        message = self.render_template_string(template.message, context)

        # Procesar botones si existen
        buttons = None
        if template.buttons:
            buttons_str = json.dumps(template.buttons)
            buttons_str = self.render_template_string(buttons_str, context)
            buttons = json.loads(buttons_str)

        return TelegramContent(
            message=message,
            parse_mode=template.parse_mode,
            disable_preview=template.disable_preview,
            buttons=buttons,
        )

    def get_recipient(self, notification: Notification, context: Dict[str, Any]) -> Optional[str]:
        """Obtiene el chat_id de Telegram del destinatario."""
        if notification.recipient_identifier:
            return notification.recipient_identifier

        if context.get("telegram_chat_id"):
            return context["telegram_chat_id"]

        # Buscar en cuentas externas del usuario
        if notification.user_id:
            try:
                from notifications.models import UserExternalAccount
                account = UserExternalAccount.objects.filter(
                    user=notification.user_id,
                    account_type="telegram",
                    is_verified=True,
                ).first()
                if account and account.external_id:
                    return account.external_id
            except Exception:
                pass

        return None

    def send(self, notification: Notification, content: TelegramContent) -> bool:
        """
        Envía el mensaje a Telegram.

        Args:
            notification: Modelo Notification.
            content: TelegramContent preparado.

        Returns:
            True si el envío fue exitoso.
        """
        try:
            provider = self.provider
            recipient = self.get_recipient(notification, notification.context_data or {})

            if not recipient:
                logger.error(f"No hay chat_id Telegram para notificación {notification.uuid}")
                notification.error_message = "No hay chat_id de Telegram configurado"
                return False

            response = provider.send(
                recipient=recipient,
                content={
                    "text": content.message,
                    "parse_mode": content.parse_mode,
                    "disable_preview": content.disable_preview,
                    "buttons": content.buttons,
                },
            )

            self.update_notification_from_response(notification, response)
            self.log_send_result(notification, response.success, response)

            # Guardar contenido renderizado
            notification.rendered_content = {
                "message": content.message,
                "chat_id": recipient,
                "parse_mode": content.parse_mode,
            }
            notification.recipient_identifier = recipient

            return response.success

        except Exception as e:
            logger.error(f"Error enviando a Telegram {notification.uuid}: {str(e)}")
            notification.error_message = str(e)
            return False
