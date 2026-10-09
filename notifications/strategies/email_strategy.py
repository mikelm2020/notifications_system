# ============================================================================
# EMAIL STRATEGY
# ============================================================================

"""
email_strategy.py - Estrategia para canal de Email.
"""

import logging
from typing import Any, Dict, Optional

from django.conf import settings

from notifications.dtos.email_content import EmailContent
from notifications.models import EmailTemplate, Notification
from notifications.providers.smtp import SMTPProvider
from notifications.strategies.base_strategy import NotificationChannelStrategy

logger = logging.getLogger(__name__)


class EmailChannelStrategy(NotificationChannelStrategy):
    """Estrategia para canal de Email usando SMTP."""

    channel_name = "email"
    provider_class = SMTPProvider

    def __init__(self, provider: Optional[SMTPProvider] = None, from_email: Optional[str] = None):
        super().__init__(provider)
        self.from_email = from_email or getattr(
            settings, "DEFAULT_FROM_EMAIL", "noreply@example.com"
        )

    def prepare_content(
        self, email_template: EmailTemplate, context: Dict[str, Any]
    ) -> EmailContent:
        """
        Prepara el contenido del email usando Django templates.

        Args:
            email_template: Modelo EmailTemplate.
            context: Variables de contexto.

        Returns:
            EmailContent con subject, body, etc.
        """
        subject = self.render_template_string(email_template.template_subject, context)
        body = self.render_template_string(email_template.template_text, context)

        html_body = None
        if email_template.template_html:
            html_body = self.render_template_string(email_template.template_html, context)

        return EmailContent(
            subject=subject,
            body=body,
            html_body=html_body,
            to_email=context.get("user_email", ""),
            from_email=self.from_email,
        )

    def get_recipient(self, notification: Notification, context: Dict[str, Any]) -> Optional[str]:
        """Obtiene el email del destinatario."""
        if notification.recipient_identifier:
            return notification.recipient_identifier

        if context.get("user_email"):
            return context["user_email"]

        if notification.user_id and hasattr(notification.user_id, "email"):
            return notification.user_id.email

        return None

    def send(self, notification: Notification, content: EmailContent) -> bool:
        """
        Envía el email.

        Args:
            notification: Modelo Notification.
            content: EmailContent preparado.

        Returns:
            True si el envío fue exitoso.
        """
        try:
            provider = self.provider
            recipient = content.to_email

            if not recipient:
                logger.error(f"No hay email de destino para notificación {notification.uuid}")
                return False

            response = provider.send(
                recipient=recipient,
                content={
                    "subject": content.subject,
                    "body": content.body,
                    "html_body": content.html_body,
                },
                from_email=content.from_email,
            )

            self.update_notification_from_response(notification, response)
            self.log_send_result(notification, response.success, response)

            # Guardar contenido renderizado para auditoría
            notification.rendered_content = {
                "subject": content.subject,
                "body_preview": content.body[:500] if content.body else "",
            }

            return response.success

        except Exception as e:
            logger.error(f"Error enviando email {notification.uuid}: {str(e)}")
            self.record_send_error(notification, e)
            return False
