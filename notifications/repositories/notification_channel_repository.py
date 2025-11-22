# ============================================================================
# REPOSITORIES - Capa de Acceso a Datos
# ============================================================================

from typing import Optional

from notifications.models import NotificationChannel

from .base_repository import BaseRepositoryBuilder


class NotificationChannelRepository(BaseRepositoryBuilder):
    """Repositorio para operaciones de NotificationChannel"""

    __model__ = NotificationChannel
    __pk_field__ = "id"

    @classmethod
    def get_by_name(cls, name: str) -> Optional[NotificationChannel]:
        """Obtiene un canal por nombre"""
        return cls.find_records(name=name, first=True)
