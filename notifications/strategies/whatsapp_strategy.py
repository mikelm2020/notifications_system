# ============================================================================
# WHATSAPP STRATEGY
# ============================================================================

"""
whatsapp_strategy.py - Estrategia para notificaciones WhatsApp.
"""

import logging
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from notifications.models import Notification, WhatsAppTemplate
from notifications.providers.twilio_provider import TwilioProvider
from notifications.strategies.base_strategy import NotificationChannelStrategy

logger = logging.getLogger(__name__)


@dataclass
class WhatsAppContent:
    """Contenido para notificación WhatsApp."""
    message: str
    to_number: str
    template_sid: Optional[str] = None
    header_type: str = "none"
    header_content: Optional[str] = None
    footer: Optional[str] = None
    buttons: Optional[List[Dict]] = None
    media_url: Optional[str] = None


class WhatsAppChannelStrategy(NotificationChannelStrategy):
    """Estrategia para canal WhatsApp usando Twilio."""

    channel_name = "whatsapp"
    provider_class = TwilioProvider

    def prepare_content(
        self,
        template: WhatsAppTemplate,
        context: Dict[str, Any]
    ) -> WhatsAppContent:
        """
        Prepara el contenido de WhatsApp.

        Args:
            template: Modelo WhatsAppTemplate.
            context: Variables de contexto.

        Returns:
            WhatsAppContent con mensaje y configuración.
        """
        message = self.render_template_string(template.message, context)

        header_content = None
        if template.header_content:
            header_content = self.render_template_string(template.header_content, context)

        return WhatsAppContent(
            message=message,
            to_number=context.get("phone_number", ""),
            template_sid=template.template_sid or None,
            header_type=template.header_type,
            header_content=header_content,
            footer=template.footer or None,
            buttons=template.buttons or None,
            media_url=context.get("media_url"),
        )

    def get_recipient(self, notification: Notification, context: Dict[str, Any]) -> Optional[str]:
        """Obtiene el número de WhatsApp del destinatario."""
        if notification.recipient_identifier:
            return notification.recipient_identifier

        if context.get("phone_number"):
            return context["phone_number"]

        if context.get("whatsapp_number"):
            return context["whatsapp_number"]

        # Buscar en cuentas externas del usuario
        if notification.user_id:
            try:
                from notifications.models import UserExternalAccount
                account = UserExternalAccount.objects.filter(
                    user=notification.user_id,
                    account_type="whatsapp",
                    is_verified=True,
                ).first()
                if account and account.phone_number:
                    return account.phone_number
            except Exception:
                pass

        return None

    def send(self, notification: Notification, content: WhatsAppContent) -> bool:
        """
        Envía el mensaje de WhatsApp.

        Args:
            notification: Modelo Notification.
            content: WhatsAppContent preparado.

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
                logger.error(f"No hay número WhatsApp para notificación {notification.uuid}")
                notification.error_message = "No hay número de WhatsApp configurado"
                return False

            # Normalizar número
            if not recipient.startswith("+"):
                recipient = f"+{recipient}"

            # Preparar contenido
            message_content = {"body": content.message}

            # Agregar media si existe
            if content.media_url:
                message_content["media_url"] = content.media_url

            # Usar template pre-aprobado si está configurado
            if content.template_sid:
                # Extraer variables del mensaje para el template
                # Los templates de WhatsApp usan {{1}}, {{2}}, etc.
                response = provider.send_whatsapp_template(
                    to=recipient,
                    template_sid=content.template_sid,
                    template_variables=notification.context_data or {},
                )
            else:
                response = provider.send_whatsapp(
                    to=recipient,
                    body=content.message,
                    media_url=content.media_url,
                )

            self.update_notification_from_response(notification, response)
            self.log_send_result(notification, response.success, response)

            # Guardar contenido renderizado
            notification.rendered_content = {
                "message": content.message,
                "to_number": recipient,
                "template_sid": content.template_sid,
            }
            notification.recipient_identifier = recipient

            return response.success

        except Exception as e:
            logger.error(f"Error enviando WhatsApp {notification.uuid}: {str(e)}")
            notification.error_message = str(e)
            return False
