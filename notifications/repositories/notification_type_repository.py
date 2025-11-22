# ============================================================================
# REPOSITORIES - Capa de Acceso a Datos
# ============================================================================

from typing import List, Optional

from notifications.models import (
    NotificationChannel,
    NotificationType,
    NotificationTypeChannels,
)

from .base_repository import BaseRepositoryBuilder


class NotificationTypeRepository(BaseRepositoryBuilder):
    """Repositorio para operaciones de NotificationType"""

    __model__ = NotificationType
    __pk_field__ = "id"

    @classmethod
    def get_by_event_code(cls, event_code: str) -> Optional[NotificationType]:
        """Obtiene tipo de notificación por código de evento"""
        return cls.find_records(event_code=event_code, first=True)

    @classmethod
    def get_channels_for_type(
        cls, notification_type_id: int
    ) -> List[NotificationChannel]:
        """Obtiene los canales asociados a un tipo de notificación"""
        channels = NotificationTypeChannels.objects.filter(
            notification_type_id=notification_type_id
        ).select_related("channel_id")
        return [ntc.channel_id for ntc in channels]
