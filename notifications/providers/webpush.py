# ============================================================================
# WEB PUSH PROVIDER
# ============================================================================

"""
webpush.py - Proveedor para Web Push Notifications.

Requiere: pip install pywebpush
"""

import json
import logging
from typing import Any, Dict, Optional

from notifications.providers.base import BaseProvider, ProviderResponse

logger = logging.getLogger(__name__)


class WebPushProvider(BaseProvider):
    """
    Proveedor para Web Push Notifications.

    Configuración en NOTIFICATIONS_CONFIG:
        "webpush": {
            "vapid_private_key": "-----BEGIN EC PRIVATE KEY-----...",
            "vapid_public_key": "BNxxxxxx...",
            "vapid_claims_email": "admin@example.com",
        }

    Para generar claves VAPID:
        from pywebpush import generate_vapid_keypair
        private_key, public_key = generate_vapid_keypair()
    """

    provider_name = "webpush"
    required_config_fields = [
        "vapid_private_key",
        "vapid_public_key",
        "vapid_claims_email",
    ]

    def get_client(self) -> Any:
        """Web Push no requiere un cliente persistente."""
        try:
            import pywebpush
            return pywebpush
        except ImportError:
            raise ImportError(
                "pywebpush no está instalado. "
                "Ejecuta: pip install pywebpush"
            )

    def send(
        self,
        recipient: str,
        content: Dict[str, Any],
        **kwargs
    ) -> ProviderResponse:
        """
        Envía una Web Push notification.

        Args:
            recipient: JSON string o dict con subscription info:
                {
                    "endpoint": "https://...",
                    "keys": {
                        "p256dh": "...",
                        "auth": "..."
                    }
                }
            content: Dict con:
                - title: Título
                - body: Cuerpo
                - icon: URL del icono
                - badge: URL del badge
                - image: URL de imagen
                - data: Datos adicionales
                - actions: Lista de acciones
                - tag: Tag para agrupar
                - requireInteraction: Boolean
            **kwargs:
                - ttl: Time to live en segundos

        Returns:
            ProviderResponse con resultado.
        """
        try:
            pywebpush = self.get_client()

            # Parsear subscription si es string
            if isinstance(recipient, str):
                subscription_info = json.loads(recipient)
            else:
                subscription_info = recipient

            # Preparar payload
            payload = {
                "notification": {
                    "title": content.get("title", ""),
                    "body": content.get("body", ""),
                }
            }

            # Agregar campos opcionales
            optional_fields = ["icon", "badge", "image", "tag", "data", "actions", "requireInteraction"]
            for field in optional_fields:
                if content.get(field):
                    payload["notification"][field] = content[field]

            # Configurar VAPID
            vapid_claims = {
                "sub": f"mailto:{self._config['vapid_claims_email']}"
            }

            # Enviar
            response = pywebpush.webpush(
                subscription_info=subscription_info,
                data=json.dumps(payload),
                vapid_private_key=self._config["vapid_private_key"],
                vapid_claims=vapid_claims,
                ttl=kwargs.get("ttl", 86400),  # Default 24 horas
            )

            logger.info(f"Web Push enviado a endpoint: {subscription_info.get('endpoint', '')[:50]}...")

            return ProviderResponse(
                success=True,
                message_id=str(response.status_code),
                raw_response={
                    "status_code": response.status_code,
                    "headers": dict(response.headers) if hasattr(response, 'headers') else {},
                }
            )

        except Exception as e:
            error_msg = str(e).lower()

            # Detectar subscripciones expiradas
            if "410" in str(e) or "gone" in error_msg:
                return ProviderResponse(
                    success=False,
                    error_message="Subscription expirada",
                    error_code="SUBSCRIPTION_EXPIRED",
                )

            if "404" in str(e) or "not found" in error_msg:
                return ProviderResponse(
                    success=False,
                    error_message="Subscription no encontrada",
                    error_code="SUBSCRIPTION_NOT_FOUND",
                )

            return self._handle_error(e, "Error enviando Web Push")

    @classmethod
    def generate_vapid_keys(cls) -> Dict[str, str]:
        """
        Genera un par de claves VAPID.

        Returns:
            Dict con 'private_key' y 'public_key'.
        """
        try:
            from pywebpush import generate_vapid_keypair
            private_key, public_key = generate_vapid_keypair()
            return {
                "private_key": private_key,
                "public_key": public_key,
            }
        except ImportError:
            raise ImportError("pywebpush no está instalado")
