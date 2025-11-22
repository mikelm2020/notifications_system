# ============================================================================
# SERVICIO ESPECIALIZADO PARA EMAIL
# ============================================================================

import logging
from typing import Any, Dict

from notifications.dtos.notification_data import NotificationData
from notifications.models import (
    Notification,
)
from notifications.repositories.email_template_repository import EmailTemplateRepository
from notifications.repositories.notification_repository import NotificationRepository
from notifications.services.notification_service import NotificationService
from notifications.strategies.email_strategy import EmailChannelStrategy

logger = logging.getLogger(__name__)


class EmailNotificationService:
    """Servicio especializado para notificaciones por email"""

    def __init__(
        self,
        notification_service: NotificationService = None,
        email_template_repo: EmailTemplateRepository = EmailTemplateRepository,
    ):
        self.notification_service = notification_service or NotificationService()
        self.email_template_repo = email_template_repo

    def send_email_notification(
        self, event_code: str, user_id: int, user_email: str, context: Dict[str, Any]
    ) -> Notification:
        """
        Método de conveniencia para enviar notificaciones por email.

        Args:
            event_code: Código del evento (ej: ORDER_CREATED)
            user_id: ID del usuario destinatario
            user_email: Email del destinatario
            context: Variables para el template
        """
        # Agregar email al contexto
        context["user_email"] = user_email

        # Crear datos de notificación
        notification_data = NotificationData(
            event_code=event_code, user_id=user_id, context=context
        )

        # Usar el servicio principal
        notifications = self.notification_service.create_and_send_notification(
            notification_data
        )

        # Retornar la notificación de email
        email_notifications = [
            n for n in notifications if n.channel_id.name.lower() == "email"
        ]

        return email_notifications[0] if email_notifications else None

    def resend_failed_email(self, notification_uuid: str) -> bool:
        """Reenvía una notificación de email fallida"""
        notification = NotificationRepository.get_by_uuid(notification_uuid)

        if not notification:
            return False

        if notification.channel_id.name.lower() != "email":
            return False

        # Obtener contexto original (deberías guardarlo en la notificación)
        # Por ahora usamos un contexto vacío
        context = {}

        try:
            strategy = EmailChannelStrategy()
            template = self.email_template_repo.get_by_notification_type(
                notification.notification_type_id.id
            )

            content = strategy.prepare_content(template, context)
            success = strategy.send(notification, content)

            if success:
                NotificationRepository.mark_as_sent(notification)
            else:
                NotificationRepository.mark_as_failed(notification)

            return success
        except Exception as e:
            logger.error(f"Error reenviando email {notification_uuid}: {str(e)}")
            return False
