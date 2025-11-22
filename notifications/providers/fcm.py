# ============================================================================
# FCM PROVIDER (Firebase Cloud Messaging)
# ============================================================================

"""
fcm.py - Proveedor para Push Notifications via Firebase Cloud Messaging.

Requiere: pip install firebase-admin
"""

import logging
from typing import Any, Dict, List, Optional

from notifications.providers.base import BaseProvider, ProviderResponse

logger = logging.getLogger(__name__)


class FCMProvider(BaseProvider):
    """
    Proveedor para Push Notifications usando Firebase Cloud Messaging.

    Configuración en NOTIFICATIONS_CONFIG:
        "fcm": {
            "credentials_path": "/path/to/service-account.json",
            # O usar dict directamente:
            "credentials": {
                "type": "service_account",
                "project_id": "...",
                ...
            },
            "project_id": "my-project",  # Opcional si está en credentials
        }
    """

    provider_name = "fcm"
    required_config_fields = []  # Credentials pueden venir de varias formas

    _app_initialized = False

    def get_client(self) -> Any:
        """Inicializa y retorna la app de Firebase."""
        if self._client is None:
            try:
                import firebase_admin
                from firebase_admin import credentials

                if not FCMProvider._app_initialized:
                    cred_path = self._config.get("credentials_path")
                    cred_dict = self._config.get("credentials")

                    if cred_path:
                        cred = credentials.Certificate(cred_path)
                    elif cred_dict:
                        cred = credentials.Certificate(cred_dict)
                    else:
                        # Intenta usar Application Default Credentials
                        cred = credentials.ApplicationDefault()

                    firebase_admin.initialize_app(cred)
                    FCMProvider._app_initialized = True

                self._client = firebase_admin.get_app()

            except ImportError:
                raise ImportError(
                    "firebase-admin no está instalado. "
                    "Ejecuta: pip install firebase-admin"
                )
        return self._client

    def send(
        self,
        recipient: str,
        content: Dict[str, Any],
        **kwargs
    ) -> ProviderResponse:
        """
        Envía una notificación Push a un dispositivo.

        Args:
            recipient: Token FCM del dispositivo.
            content: Dict con:
                - title: Título de la notificación
                - body: Cuerpo del mensaje
                - image: URL de imagen (opcional)
                - data: Datos adicionales (opcional)
                - click_action: URL/deep link (opcional)
            **kwargs:
                - android: Configuración específica de Android
                - apns: Configuración específica de iOS
                - webpush: Configuración específica de Web

        Returns:
            ProviderResponse con resultado.
        """
        try:
            from firebase_admin import messaging

            self.get_client()  # Asegurar inicialización

            # Construir notificación
            notification = messaging.Notification(
                title=content.get("title"),
                body=content.get("body"),
                image=content.get("image"),
            )

            # Construir mensaje
            message = messaging.Message(
                token=recipient,
                notification=notification,
                data=content.get("data"),
                android=kwargs.get("android"),
                apns=kwargs.get("apns"),
                webpush=kwargs.get("webpush"),
            )

            # Enviar
            response = messaging.send(message)

            logger.info(f"FCM enviado: {response}")

            return ProviderResponse(
                success=True,
                message_id=response,
            )

        except Exception as e:
            error_msg = str(e)

            # Detectar tokens inválidos
            if "not a valid FCM registration token" in error_msg.lower():
                return ProviderResponse(
                    success=False,
                    error_message="Token FCM inválido",
                    error_code="INVALID_TOKEN",
                )

            if "requested entity was not found" in error_msg.lower():
                return ProviderResponse(
                    success=False,
                    error_message="Token FCM no registrado",
                    error_code="UNREGISTERED",
                )

            return self._handle_error(e, f"Error enviando FCM a {recipient[:20]}...")

    def send_multicast(
        self,
        tokens: List[str],
        content: Dict[str, Any],
        **kwargs
    ) -> Dict[str, ProviderResponse]:
        """
        Envía una notificación a múltiples dispositivos.

        Args:
            tokens: Lista de tokens FCM.
            content: Contenido de la notificación.

        Returns:
            Dict con token -> ProviderResponse.
        """
        try:
            from firebase_admin import messaging

            self.get_client()

            notification = messaging.Notification(
                title=content.get("title"),
                body=content.get("body"),
                image=content.get("image"),
            )

            message = messaging.MulticastMessage(
                tokens=tokens,
                notification=notification,
                data=content.get("data"),
            )

            response = messaging.send_each_for_multicast(message)

            results = {}
            for idx, send_response in enumerate(response.responses):
                token = tokens[idx]
                if send_response.success:
                    results[token] = ProviderResponse(
                        success=True,
                        message_id=send_response.message_id,
                    )
                else:
                    results[token] = ProviderResponse(
                        success=False,
                        error_message=str(send_response.exception),
                    )

            logger.info(
                f"FCM multicast: {response.success_count} exitosos, "
                f"{response.failure_count} fallidos"
            )

            return results

        except Exception as e:
            logger.error(f"Error en FCM multicast: {e}")
            return {
                token: ProviderResponse(success=False, error_message=str(e))
                for token in tokens
            }

    def send_to_topic(
        self,
        topic: str,
        content: Dict[str, Any],
        **kwargs
    ) -> ProviderResponse:
        """
        Envía una notificación a un topic.

        Args:
            topic: Nombre del topic.
            content: Contenido de la notificación.
        """
        try:
            from firebase_admin import messaging

            self.get_client()

            notification = messaging.Notification(
                title=content.get("title"),
                body=content.get("body"),
            )

            message = messaging.Message(
                topic=topic,
                notification=notification,
                data=content.get("data"),
            )

            response = messaging.send(message)

            return ProviderResponse(
                success=True,
                message_id=response,
            )

        except Exception as e:
            return self._handle_error(e, f"Error enviando a topic {topic}")
