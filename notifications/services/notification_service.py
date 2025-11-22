# ============================================================================
# SERVICES - Capa de Lógica de Negocio
# ============================================================================

"""
notification_service.py - Servicio principal de notificaciones.
"""

import logging
import uuid as uuid_lib
from typing import Any, Dict, List, Optional

from notifications.conf import notifications_config
from notifications.dtos.notification_data import NotificationData
from notifications.exceptions import (
    NoChannelsConfiguredError,
    NotificationTypeNotFoundError,
    TemplateNotFoundError,
)
from notifications.factories.channel_factory import NotificationChannelFactory
from notifications.models import (
    EmailTemplate,
    InAppTemplate,
    Notification,
    NotificationChannel,
    NotificationType,
    PushTemplate,
    SlackTemplate,
    SMSTemplate,
    TelegramTemplate,
    UserNotificationPreference,
    WebhookTemplate,
    WhatsAppTemplate,
)
from notifications.repositories.notification_channel_repository import (
    NotificationChannelRepository,
)
from notifications.repositories.notification_repository import NotificationRepository
from notifications.repositories.notification_type_repository import (
    NotificationTypeRepository,
)

logger = logging.getLogger(__name__)


# Mapeo de canales a modelos de template
CHANNEL_TEMPLATE_MAP = {
    "email": EmailTemplate,
    "in_app": InAppTemplate,
    "sms": SMSTemplate,
    "push_fcm": PushTemplate,
    "push_web": PushTemplate,
    "whatsapp": WhatsAppTemplate,
    "slack": SlackTemplate,
    "telegram": TelegramTemplate,
    "webhook": WebhookTemplate,
}


class NotificationService:
    """
    Servicio principal de notificaciones.
    Implementa Template Method Pattern para el flujo de envío.
    """

    def __init__(
        self,
        notification_repo: NotificationRepository = NotificationRepository,
        notification_type_repo: NotificationTypeRepository = NotificationTypeRepository,
        channel_repo: NotificationChannelRepository = NotificationChannelRepository,
        channel_factory: NotificationChannelFactory = NotificationChannelFactory,
    ):
        self.notification_repo = notification_repo
        self.notification_type_repo = notification_type_repo
        self.channel_repo = channel_repo
        self.channel_factory = channel_factory

    def create_and_send_notification(
        self,
        notification_data: NotificationData,
        channels: Optional[List[str]] = None,
    ) -> List[Notification]:
        """
        Template Method: Flujo completo de creación y envío.

        1. Valida el tipo de notificación
        2. Obtiene los canales configurados
        3. Filtra por preferencias del usuario
        4. Crea notificaciones por cada canal
        5. Envía cada notificación

        Args:
            notification_data: Datos de la notificación.
            channels: Lista de canales específicos (opcional).

        Returns:
            Lista de notificaciones creadas.
        """
        # Emitir signal pre-create
        from notifications.signals import notification_pre_create
        notification_pre_create.send(
            sender=self.__class__,
            notification_data=notification_data,
        )

        # Paso 1: Validar tipo de notificación
        notification_type = self._validate_notification_type(
            notification_data.event_code
        )

        # Paso 2: Obtener canales
        if channels:
            available_channels = self._get_channels_by_names(channels)
        else:
            available_channels = self._get_channels_for_type(notification_type)

        # Paso 3: Filtrar por preferencias del usuario
        if notification_data.user_id:
            available_channels = self._filter_by_user_preferences(
                notification_data.user_id,
                notification_type,
                available_channels,
            )

        # Paso 4: Crear notificaciones
        notifications = self._create_notifications(
            notification_type, available_channels, notification_data
        )

        # Emitir signal post-create
        from notifications.signals import notification_post_create
        for notification in notifications:
            notification_post_create.send(
                sender=self.__class__,
                notification=notification,
                notification_data=notification_data,
            )

        # Paso 5: Enviar notificaciones (si no están programadas)
        for notification in notifications:
            if not notification.scheduled_for:
                self._send_notification(notification, notification_data.context)

        return notifications

    def _validate_notification_type(self, event_code: str) -> NotificationType:
        """Valida y obtiene el tipo de notificación."""
        notification_type = self.notification_type_repo.get_by_event_code(event_code)
        if not notification_type:
            raise NotificationTypeNotFoundError(event_code)
        if not notification_type.is_active:
            raise NotificationTypeNotFoundError(event_code)
        return notification_type

    def _get_channels_for_type(
        self, notification_type: NotificationType
    ) -> List[NotificationChannel]:
        """Obtiene los canales configurados para el tipo."""
        channels = self.notification_type_repo.get_channels_for_type(
            notification_type.id
        )

        # Filtrar solo canales habilitados en configuración
        enabled_channels = notifications_config.get_enabled_channels()
        channels = [ch for ch in channels if ch.name in enabled_channels]

        if not channels:
            raise NoChannelsConfiguredError(notification_type.event_code)
        return channels

    def _get_channels_by_names(self, channel_names: List[str]) -> List[NotificationChannel]:
        """Obtiene canales por nombre."""
        channels = NotificationChannel.objects.filter(
            name__in=channel_names,
            is_active=True,
        )
        return list(channels)

    def _filter_by_user_preferences(
        self,
        user_id: int,
        notification_type: NotificationType,
        channels: List[NotificationChannel],
    ) -> List[NotificationChannel]:
        """Filtra canales según preferencias del usuario."""
        # Obtener preferencias deshabilitadas
        disabled_prefs = UserNotificationPreference.objects.filter(
            user_id=user_id,
            is_enabled=False,
        ).filter(
            # Preferencia global del canal O específica del tipo
            models_Q(notification_type__isnull=True) |
            models_Q(notification_type=notification_type)
        ).values_list("channel_id", flat=True)

        # Filtrar canales no deshabilitados
        return [ch for ch in channels if ch.id not in disabled_prefs]

    def _create_notifications(
        self,
        notification_type: NotificationType,
        channels: List[NotificationChannel],
        notification_data: NotificationData,
    ) -> List[Notification]:
        """Crea registros de notificación para cada canal."""
        notifications = []
        notification_uuid = notification_data.uuid or str(uuid_lib.uuid4())

        for channel in channels:
            notification = Notification(
                uuid=notification_uuid,
                notification_type_id=notification_type,
                user_id_id=notification_data.user_id,
                channel_id=channel,
                status=Notification.Status.PENDING,
                context_data=notification_data.context,
                scheduled_for=notification_data.scheduled_for,
            )
            saved_notification = self.notification_repo.save_record(notification)
            notifications.append(saved_notification)

        return notifications

    def _send_notification(self, notification: Notification, context: Dict[str, Any]):
        """Envía una notificación usando la estrategia apropiada."""
        from notifications.signals import notification_post_send, notification_pre_send

        try:
            # Crear estrategia
            strategy = self.channel_factory.create(
                notification.channel_id.name,
                check_enabled=False,  # Ya verificamos arriba
            )

            # Obtener template
            template = self._get_template_for_channel(
                notification.notification_type_id,
                notification.channel_id.name
            )

            # Preparar contenido
            content = strategy.prepare_content(template, context)

            # Emitir signal pre-send
            notification_pre_send.send(
                sender=strategy.__class__,
                notification=notification,
                content=content,
            )

            # Actualizar estado a "enviando"
            notification.status = Notification.Status.SENDING
            notification.save(update_fields=["status", "updated_at"])

            # Enviar
            success = strategy.send(notification, content)

            # Actualizar estado
            if success:
                self.notification_repo.mark_as_sent(notification)
            else:
                self.notification_repo.mark_as_failed(notification)

            # Emitir signal post-send
            notification_post_send.send(
                sender=strategy.__class__,
                notification=notification,
                success=success,
            )

        except Exception as e:
            logger.error(f"Error procesando notificación {notification.uuid}: {str(e)}")
            notification.error_message = str(e)
            self.notification_repo.mark_as_failed(notification)

    def _get_template_for_channel(
        self, notification_type: NotificationType, channel_name: str
    ):
        """Obtiene el template apropiado según el canal."""
        channel_name_lower = channel_name.lower()
        template_model = CHANNEL_TEMPLATE_MAP.get(channel_name_lower)

        if not template_model:
            raise TemplateNotFoundError(notification_type.event_code, channel_name)

        template = template_model.objects.filter(
            notification_type_id=notification_type,
            is_active=True,
        ).first()

        if not template:
            raise TemplateNotFoundError(notification_type.event_code, channel_name)

        return template

    def get_user_notifications(
        self, user_id: int, unread_only: bool = False
    ) -> List[Notification]:
        """Obtiene notificaciones de un usuario."""
        if unread_only:
            return self.notification_repo.get_user_notifications(user_id, is_read=False)
        return self.notification_repo.get_user_notifications(user_id)

    def mark_notification_as_read(self, notification_uuid: str) -> bool:
        """Marca una notificación como leída."""
        notification = self.notification_repo.get_by_uuid(notification_uuid)
        if not notification:
            return False
        self.notification_repo.mark_as_read(notification)
        return True


# Importar Q aquí para evitar problemas de import circular
from django.db.models import Q as models_Q
