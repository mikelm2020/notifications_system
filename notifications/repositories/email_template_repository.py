# ============================================================================
# REPOSITORIES - Capa de Acceso a Datos
# ============================================================================

from typing import Optional

from notifications.models import EmailTemplate

from .base_repository import BaseRepositoryBuilder


class EmailTemplateRepository(BaseRepositoryBuilder):
    """Repositorio para operaciones de EmailTemplate"""

    __model__ = EmailTemplate
    __pk_field__ = "id"

    @classmethod
    def get_by_notification_type(
        cls, notification_type_id: int
    ) -> Optional[EmailTemplate]:
        """Obtiene template por tipo de notificación"""
        return cls.find_records(notification_type_id=notification_type_id, first=True)

    @classmethod
    def get_by_event_code(cls, event_code: str) -> Optional[EmailTemplate]:
        """Obtiene template por código de evento"""
        return cls.find_records(notification_type_id__event_code=event_code, first=True)
