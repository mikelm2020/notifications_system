# ============================================================================
# BASE PROVIDER
# ============================================================================

"""
base.py - Clase base abstracta para proveedores de notificación.

Los proveedores encapsulan la comunicación con servicios externos
(Twilio, Firebase, etc.) y pueden ser intercambiados fácilmente.
"""

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, Dict, Optional

from notifications.conf import notifications_config
from notifications.exceptions import (
    ProviderConnectionError,
    ProviderNotConfiguredError,
)

logger = logging.getLogger(__name__)


@dataclass
class ProviderResponse:
    """Respuesta estándar de un proveedor."""
    success: bool
    message_id: Optional[str] = None
    error_message: Optional[str] = None
    error_code: Optional[str] = None
    raw_response: Optional[Dict[str, Any]] = None


class BaseProvider(ABC):
    """
    Clase base para todos los proveedores de notificación.

    Cada proveedor debe implementar:
    - send(): Envía un mensaje
    - validate_config(): Valida la configuración
    - is_available(): Verifica si el servicio está disponible
    """

    provider_name: str = "base"
    required_config_fields: list = []

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        """
        Inicializa el proveedor con configuración.

        Args:
            config: Configuración del proveedor. Si es None, se obtiene
                   de NOTIFICATIONS_CONFIG.
        """
        self._config = config or self._load_config()
        self._client = None

    def _load_config(self) -> Dict[str, Any]:
        """Carga la configuración del proveedor desde settings."""
        config = notifications_config.get_provider_config(self.provider_name)
        return config or {}

    def validate_config(self) -> bool:
        """
        Valida que la configuración tenga todos los campos requeridos.

        Raises:
            ProviderNotConfiguredError: Si faltan campos requeridos.
        """
        missing = [
            field for field in self.required_config_fields
            if not self._config.get(field)
        ]
        if missing:
            raise ProviderNotConfiguredError(
                self.provider_name,
                missing_fields=missing
            )
        return True

    @property
    def config(self) -> Dict[str, Any]:
        """Retorna la configuración del proveedor."""
        return self._config

    @abstractmethod
    def get_client(self) -> Any:
        """
        Obtiene o crea el cliente del proveedor.

        Returns:
            Cliente inicializado del proveedor.
        """
        pass

    @abstractmethod
    def send(
        self,
        recipient: str,
        content: Dict[str, Any],
        **kwargs
    ) -> ProviderResponse:
        """
        Envía un mensaje a través del proveedor.

        Args:
            recipient: Identificador del destinatario.
            content: Contenido del mensaje.
            **kwargs: Argumentos adicionales específicos del proveedor.

        Returns:
            ProviderResponse con el resultado del envío.
        """
        pass

    def is_available(self) -> bool:
        """
        Verifica si el proveedor está disponible y configurado.

        Returns:
            True si el proveedor está listo para usar.
        """
        try:
            self.validate_config()
            return True
        except ProviderNotConfiguredError:
            return False

    def _handle_error(self, error: Exception, context: str = "") -> ProviderResponse:
        """
        Maneja errores de manera consistente.

        Args:
            error: Excepción capturada.
            context: Contexto adicional para el log.

        Returns:
            ProviderResponse con información del error.
        """
        error_msg = f"{self.provider_name}: {str(error)}"
        if context:
            error_msg = f"{context} - {error_msg}"

        logger.error(error_msg, exc_info=True)

        return ProviderResponse(
            success=False,
            error_message=str(error),
            error_code=type(error).__name__,
        )


class MockProvider(BaseProvider):
    """
    Proveedor mock para testing y desarrollo.

    Simula el envío sin conectar a servicios externos.
    """

    provider_name = "mock"
    required_config_fields = []

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        super().__init__(config or {})
        self.sent_messages = []

    def get_client(self) -> Any:
        return None

    def send(
        self,
        recipient: str,
        content: Dict[str, Any],
        **kwargs
    ) -> ProviderResponse:
        """Simula envío y guarda el mensaje."""
        message = {
            "recipient": recipient,
            "content": content,
            "kwargs": kwargs,
        }
        self.sent_messages.append(message)

        logger.info(f"[MOCK] Mensaje enviado a {recipient}")

        return ProviderResponse(
            success=True,
            message_id=f"mock_{len(self.sent_messages)}",
            raw_response=message,
        )

    def clear_messages(self):
        """Limpia los mensajes enviados (para tests)."""
        self.sent_messages = []
