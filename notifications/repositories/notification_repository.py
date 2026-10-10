# ============================================================================
# REPOSITORIES - Capa de Acceso a Datos
# ============================================================================

from datetime import timedelta
from typing import List, Optional

from django.db.models import Case, F, Q, Value, When
from django.utils import timezone

from notifications.conf import notifications_config
from notifications.exceptions import AMBIGUOUS_DELIVERY_CODES
from notifications.models import Notification

from .base_repository import BaseRepositoryBuilder


class NotificationRepository(BaseRepositoryBuilder):
    """Repositorio para operaciones de Notification"""

    __model__ = Notification
    __pk_field__ = "id"

    @classmethod
    def get_by_uuid(cls, uuid: str) -> Optional[Notification]:
        """Obtiene una notificación por UUID"""
        return cls.find_records(uuid=uuid, first=True)

    @classmethod
    def get_pending_by_channel(cls, channel_name: str) -> List[Notification]:
        """Obtiene notificaciones pendientes por canal"""
        return cls.find_records(channel_id__name=channel_name, status=Notification.Status.PENDING)

    @classmethod
    def get_user_notifications(
        cls, user_id: int, is_read: Optional[bool] = None
    ) -> List[Notification]:
        """Obtiene notificaciones de un usuario"""
        filters = {"user_id": user_id}
        if is_read is not None:
            filters["is_read"] = is_read
        return cls.find_records(**filters)

    @classmethod
    def get_or_create_delivery(cls, delivery_uuid, channel, defaults):
        notification, _ = Notification.objects.get_or_create(
            uuid=delivery_uuid,
            channel_id=channel,
            defaults=defaults,
        )
        return notification

    @classmethod
    def claim_for_send(cls, notification: Notification) -> bool:
        """Compare-and-update: only one worker can claim a due record."""
        now = timezone.now()
        due = Q(scheduled_for__isnull=True) | Q(scheduled_for__lte=now)
        rows = Notification.objects.filter(
            pk=notification.pk,
            failed_permanently_at__isnull=True,
        ).filter(due)
        claimed = rows.filter(
            status__in=[Notification.Status.PENDING, Notification.Status.QUEUED]
        ).update(
            status=Notification.Status.SENDING,
            updated_at=now,
            dispatch_started_at=None,
            error_message="",
            error_code="",
        )
        if not claimed:
            claimed = (
                rows.filter(
                    status=Notification.Status.FAILED,
                    retry_count__lt=notifications_config.max_retries,
                    updated_at__lte=now - timedelta(seconds=notifications_config.retry_delay),
                )
                .exclude(error_code__in=AMBIGUOUS_DELIVERY_CODES)
                .update(
                    status=Notification.Status.SENDING,
                    retry_count=F("retry_count") + 1,
                    updated_at=now,
                    dispatch_started_at=None,
                    error_message="",
                    error_code="",
                )
            )
        notification.refresh_from_db()
        return bool(claimed)

    @classmethod
    def begin_dispatch(cls, notification: Notification) -> bool:
        """Linearization point: cancellation wins until this committed UPDATE."""
        started = timezone.now()
        updated = Notification.objects.filter(
            pk=notification.pk,
            status=Notification.Status.SENDING,
            dispatch_started_at__isnull=True,
            failed_permanently_at__isnull=True,
        ).update(dispatch_started_at=started, updated_at=started)
        notification.refresh_from_db()
        return bool(updated)

    @classmethod
    def cancel(cls, notification: Notification, reason="Cancelled") -> bool:
        before_dispatch = Q(
            status__in=[
                Notification.Status.PENDING,
                Notification.Status.QUEUED,
                Notification.Status.FAILED,
            ]
        ) | Q(status=Notification.Status.SENDING, dispatch_started_at__isnull=True)
        updated = (
            Notification.objects.filter(
                pk=notification.pk,
                failed_permanently_at__isnull=True,
            )
            .filter(before_dispatch)
            .update(
                status=Notification.Status.CANCELLED,
                error_message=reason,
                updated_at=timezone.now(),
            )
        )
        notification.refresh_from_db()
        return bool(updated)

    @classmethod
    def _owned_dispatch(cls, notification):
        return Notification.objects.filter(
            pk=notification.pk,
            status=Notification.Status.SENDING,
            dispatch_started_at=notification.dispatch_started_at,
        )

    @classmethod
    def mark_as_sent(cls, notification: Notification) -> Notification:
        if notification.dispatch_started_at is not None:
            cls._owned_dispatch(notification).update(
                status=Case(
                    When(is_read=True, then=Value(Notification.Status.READ)),
                    default=Value(Notification.Status.SENT),
                ),
                sent_at=timezone.now(),
                updated_at=timezone.now(),
                external_id=notification.external_id,
                rendered_content=notification.rendered_content,
                recipient_identifier=notification.recipient_identifier,
                error_message="",
                error_code="",
            )
        notification.refresh_from_db()
        return notification

    @classmethod
    def mark_as_failed(cls, notification: Notification) -> Notification:
        cls._owned_dispatch(notification).update(
            status=Notification.Status.FAILED,
            updated_at=timezone.now(),
            error_message=notification.error_message,
            error_code=notification.error_code,
            external_id=notification.external_id,
            rendered_content=notification.rendered_content,
        )
        notification.refresh_from_db()
        return notification

    @classmethod
    def mark_as_unknown(cls, notification: Notification) -> Notification:
        cls._owned_dispatch(notification).update(
            error_message=notification.error_message,
            error_code="DELIVERY_UNKNOWN",
            updated_at=timezone.now(),
            external_id=notification.external_id,
            rendered_content=notification.rendered_content,
        )
        notification.refresh_from_db()
        return notification

    @classmethod
    def finalize_failure(cls, notification: Notification) -> bool:
        """Persist the terminal decision before emitting the permanent failure signal."""
        updated = Notification.objects.filter(
            pk=notification.pk,
            status=Notification.Status.FAILED,
            failed_permanently_at__isnull=True,
        ).update(failed_permanently_at=timezone.now(), updated_at=timezone.now())
        notification.refresh_from_db()
        return bool(updated)

    @classmethod
    def mark_as_read(cls, notification: Notification) -> Notification:
        rows = Notification.objects.filter(pk=notification.pk)
        rows.update(is_read=True, read_at=timezone.now(), updated_at=timezone.now())
        rows.filter(status__in=[Notification.Status.SENT, Notification.Status.DELIVERED]).update(
            status=Notification.Status.READ
        )
        notification.refresh_from_db()
        return notification
