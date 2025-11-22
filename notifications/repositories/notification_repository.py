# ============================================================================
# REPOSITORIES - Capa de Acceso a Datos
# ============================================================================

from datetime import datetime
from typing import List, Optional

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
        return cls.find_records(
            channel_id__name=channel_name, status=Notification.Status.PENDING
        )

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
    def mark_as_sent(cls, notification: Notification) -> Notification:
        """Marca una notificación como enviada"""
        notification.status = Notification.Status.SENT
        notification.sent_at = datetime.now()
        return cls.save_record(notification)

    @classmethod
    def mark_as_failed(cls, notification: Notification) -> Notification:
        """Marca una notificación como fallida"""
        notification.status = Notification.Status.FAILED
        return cls.save_record(notification)

    @classmethod
    def mark_as_read(cls, notification: Notification) -> Notification:
        """Marca una notificación como leída"""
        notification.is_read = True
        notification.status = Notification.Status.READ
        return cls.save_record(notification)
