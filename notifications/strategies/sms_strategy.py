# ============================================================================
# SMS STRATEGY
# ============================================================================

"""
sms_strategy.py - Estrategia para canal SMS.
"""

import logging
from dataclasses import dataclass
from typing import Any, Dict, Optional

from notifications.models import Notification, SMSTemplate
from notifications.providers.twilio_provider import TwilioProvider
from notifications.strategies.base_strategy import NotificationChannelStrategy

logger = logging.getLogger(__name__)


@dataclass
class SMSContent:
    """Contenido para notificación SMS."""
    message: str
    to_number: str


class SMSChannelStrategy(NotificationChannelStrategy):
    """Estrategia para canal SMS usando Twilio."""

    channel_name = "sms"
    provider_class = TwilioProvider

    def prepare_content(
        self,
        template: SMSTemplate,
        context: Dict[str, Any]
    ) -> SMSContent:
        """
        Prepara el contenido del SMS.

        Args:
            template: Modelo SMSTemplate.
            context: Variables de contexto.

        Returns:
            SMSContent con mensaje y número.
        """
        message = self.render_template_string(template.message, context)

        # Truncar a 160 caracteres si es necesario
        if len(message) > 160:
            logger.warning(
                f"SMS truncado de {len(message)} a 160 caracteres "
                f"para template {template.id}"
            )
            message = message[:157] + "..."

        return SMSContent(
            message=message,
            to_number=context.get("phone_number", ""),
        )

    def get_recipient(self, notification: Notification, context: Dict[str, Any]) -> Optional[str]:
        """Obtiene el número de teléfono del destinatario."""
        if notification.recipient_identifier:
            return notification.recipient_identifier

        if context.get("phone_number"):
            return context["phone_number"]

        # Intentar obtener de cuenta externa del usuario
        if notification.user_id:
            try:
                from notifications.models import UserExternalAccount
                account = UserExternalAccount.objects.filter(
                    user=notification.user_id,
                    account_type="whatsapp",  # WhatsApp tiene el teléfono
                    is_verified=True,
                ).first()
                if account and account.phone_number:
                    return account.phone_number
            except Exception:
                pass

        return None

    def send(self, notification: Notification, content: SMSContent) -> bool:
        """
        Envía el SMS.

        Args:
            notification: Modelo Notification.
            content: SMSContent preparado.

        Returns:
            True si el envío fue exitoso.
        """
        try:
            provider = self.provider
            recipient = content.to_number or self.get_recipient(
                notification,
                notification.context_data or {}
            )

            if not recipient:
                logger.error(f"No hay número de teléfono para notificación {notification.uuid}")
                notification.error_message = "No hay número de teléfono configurado"
                return False

            # Normalizar número (asegurar formato E.164)
            if not recipient.startswith("+"):
                recipient = f"+{recipient}"

            response = provider.send_sms(
                to=recipient,
                body=content.message,
            )

            self.update_notification_from_response(notification, response)
            self.log_send_result(notification, response.success, response)

            # Guardar contenido renderizado
            notification.rendered_content = {
                "message": content.message,
                "to_number": recipient,
            }
            notification.recipient_identifier = recipient

            return response.success

        except Exception as e:
            logger.error(f"Error enviando SMS {notification.uuid}: {str(e)}")
            notification.error_message = str(e)
            return False
