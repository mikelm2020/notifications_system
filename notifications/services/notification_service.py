# ============================================================================
# SERVICES - Capa de Lógica de Negocio
# ============================================================================

"""
notification_service.py - Servicio principal de notificaciones.
"""

import logging
import uuid as uuid_lib
from typing import Any, Dict, List, Optional

from django.db import transaction
from django.db.models import Q as models_Q

from notifications.conf import notifications_config
from notifications.dtos.notification_data import NotificationData
from notifications.exceptions import (
    NoChannelsConfiguredError,
    NotificationTypeNotFoundError,
    TemplateNotFoundError,
    is_ambiguous_delivery_error,
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

    def create_and_send_notification(self, notification_data, channels=None, *, enqueue=False):
        """Persist all deliveries atomically; dispatch only after the outer commit."""
        connection = transaction.get_connection()
        if not connection.get_autocommit() and not connection.in_atomic_block:
            raise RuntimeError("Manual transactions are unsupported; use transaction.atomic()")
        deferred = enqueue or transaction.get_connection().in_atomic_block
        with transaction.atomic():
            notifications = self._create_and_queue_notification(notification_data, channels)
            for notification in notifications:
                if deferred:
                    transaction.on_commit(lambda pk=notification.pk: self._publish_dispatch(pk))
                else:
                    transaction.on_commit(
                        lambda n=notification: self._send_notification(n, n.context_data)
                    )
        return notifications

    @staticmethod
    def _publish_dispatch(pk):
        from notifications.tasks import dispatch_notification

        try:
            dispatch_notification.delay(pk)
        except Exception:
            logger.exception("Broker unavailable; delivery %s remains recoverable", pk)

    def _create_and_queue_notification(
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
        notification_type = self._validate_notification_type(notification_data.event_code)

        # A retry must retain the original delivery set, even if preferences changed.
        existing = (
            list(
                Notification.objects.filter(uuid=notification_data.uuid).select_related(
                    "channel_id",
                    "notification_type_id",
                )
            )
            if notification_data.uuid
            else []
        )
        if existing:
            if any(
                n.notification_type_id_id != notification_type.pk
                or n.user_id_id != notification_data.user_id
                for n in existing
            ):
                raise ValueError("Notification UUID already belongs to another event or user")
            return existing

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
        channels = self.notification_type_repo.get_channels_for_type(notification_type.id)

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
        disabled_prefs = (
            UserNotificationPreference.objects.filter(
                user_id=user_id,
                is_enabled=False,
            )
            .filter(
                # Preferencia global del canal O específica del tipo
                models_Q(notification_type__isnull=True)
                | models_Q(notification_type=notification_type)
            )
            .values_list("channel_id", flat=True)
        )

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
            saved_notification = self.notification_repo.get_or_create_delivery(
                notification_uuid,
                channel,
                defaults={
                    "notification_type_id": notification_type,
                    "user_id_id": notification_data.user_id,
                    "status": Notification.Status.QUEUED,
                    "context_data": notification_data.context,
                    "scheduled_for": notification_data.scheduled_for,
                },
            )
            if (
                saved_notification.notification_type_id_id != notification_type.pk
                or saved_notification.user_id_id != notification_data.user_id
            ):
                raise ValueError("Notification UUID already belongs to another event or user")
            notifications.append(saved_notification)

        return notifications

    def _send_notification(self, notification: Notification, context: Dict[str, Any]):
        """Envía una notificación usando la estrategia apropiada."""
        if transaction.get_connection().in_atomic_block:
            # Persist intent in the caller's transaction; rollback discards both.
            Notification.objects.filter(
                pk=notification.pk,
                status=Notification.Status.PENDING,
                failed_permanently_at__isnull=True,
            ).update(status=Notification.Status.QUEUED)
            transaction.on_commit(lambda: self._publish_dispatch(notification.pk))
            return False
        if not transaction.get_connection().get_autocommit():
            raise RuntimeError("Dispatch requires autocommit")
        from notifications.signals import notification_post_send, notification_pre_send

        if not self._recipient_enabled(notification):
            self.notification_repo.cancel(notification, "User disabled this channel")
            return False
        if not self.notification_repo.claim_for_send(notification):
            return False

        context = notification.context_data or context
        strategy = None
        try:
            # Crear estrategia
            strategy = self.channel_factory.create(
                notification.channel_id.name,
                check_enabled=False,  # Ya verificamos arriba
            )

            # Obtener template
            template = self._get_template_for_channel(
                notification.notification_type_id, notification.channel_id.name
            )

            # Preparar contenido
            content = strategy.prepare_content(template, context)

            # Emitir signal pre-send
            notification_pre_send.send(
                sender=strategy.__class__,
                notification=notification,
                content=content,
            )

            # Recheck after pre-send hooks. No row lock is held during provider I/O.
            if not self._recipient_enabled(notification):
                self.notification_repo.cancel(notification, "User disabled this channel")
                return False
            if not self.notification_repo.begin_dispatch(notification):
                return False
            success = strategy.send(notification, content)

        except Exception as e:
            logger.exception("Error procesando notificación %s", notification.uuid)
            notification.error_message = str(e)
            if notification.dispatch_started_at is not None and is_ambiguous_delivery_error(e):
                self.notification_repo.mark_as_unknown(notification)
            else:
                self.notification_repo.mark_as_failed(notification)
            success = False

        else:
            # If persistence fails after provider acceptance, leave SENDING for review.
            # Automatically retrying that unknown outcome could send twice.
            if success:
                self.notification_repo.mark_as_sent(notification)
            elif notification.error_code == "DELIVERY_UNKNOWN":
                self.notification_repo.mark_as_unknown(notification)
            else:
                self.notification_repo.mark_as_failed(notification)

        if (
            notification.status == Notification.Status.FAILED
            and notification.retry_count >= notifications_config.max_retries
        ):
            self.finalize_failure(notification)

        # Observer failures must never turn a confirmed send into a retriable failure.
        notification_post_send.send_robust(
            sender=strategy.__class__ if strategy is not None else self.__class__,
            notification=notification,
            success=success,
        )
        return True

    def _recipient_enabled(self, notification):
        if not notification.user_id_id:
            return True
        return bool(
            self._filter_by_user_preferences(
                notification.user_id_id,
                notification.notification_type_id,
                [notification.channel_id],
            )
        )

    def finalize_failure(self, notification, notification_data=None):
        if self.notification_repo.finalize_failure(notification):
            from notifications.signals import notification_failed_permanently

            notification_failed_permanently.send_robust(
                sender=self.__class__,
                notification=notification,
                notification_data=notification_data,
                error=RuntimeError(notification.error_message or "Retry budget exhausted"),
            )

    def _get_template_for_channel(self, notification_type: NotificationType, channel_name: str):
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

    def get_user_notifications(self, user_id: int, unread_only: bool = False) -> List[Notification]:
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
