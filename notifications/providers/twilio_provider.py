# ============================================================================
# TWILIO PROVIDER
# ============================================================================

"""
twilio_provider.py - Proveedor para SMS y WhatsApp via Twilio.

Requiere: pip install twilio
"""

import logging
from typing import Any, Dict, Optional

from notifications.providers.base import BaseProvider, ProviderResponse

logger = logging.getLogger(__name__)


class TwilioProvider(BaseProvider):
    """
    Proveedor para SMS y WhatsApp usando Twilio.

    Configuración en NOTIFICATIONS_CONFIG:
        "twilio": {
            "account_sid": "ACxxxxx",
            "auth_token": "xxxxx",
            "from_number": "+1234567890",
            "whatsapp_from": "whatsapp:+1234567890",
            "messaging_service_sid": "MGxxxxx",  # Opcional
        }
    """

    provider_name = "twilio"
    required_config_fields = ["account_sid", "auth_token"]

    def get_client(self) -> Any:
        """Obtiene el cliente de Twilio."""
        if self._client is None:
            try:
                from twilio.rest import Client
                self._client = Client(
                    self._config["account_sid"],
                    self._config["auth_token"]
                )
            except ImportError:
                raise ImportError(
                    "twilio no está instalado. "
                    "Ejecuta: pip install twilio"
                )
        return self._client

    def send(
        self,
        recipient: str,
        content: Dict[str, Any],
        **kwargs
    ) -> ProviderResponse:
        """
        Envía un mensaje SMS o WhatsApp.

        Args:
            recipient: Número de teléfono (+1234567890 para SMS,
                      whatsapp:+1234567890 para WhatsApp).
            content: Dict con:
                - body: Texto del mensaje
                - media_url: URL de media (opcional, para MMS/WhatsApp)
            **kwargs:
                - channel: "sms" o "whatsapp" (default: "sms")
                - from_number: Número remitente (opcional)

        Returns:
            ProviderResponse con resultado.
        """
        try:
            client = self.get_client()
            channel = kwargs.get("channel", "sms")

            # Determinar número de origen
            if channel == "whatsapp":
                from_number = kwargs.get(
                    "from_number",
                    self._config.get("whatsapp_from")
                )
                # Asegurar formato whatsapp:
                if not recipient.startswith("whatsapp:"):
                    recipient = f"whatsapp:{recipient}"
            else:
                from_number = kwargs.get(
                    "from_number",
                    self._config.get("from_number")
                )

            # Preparar parámetros del mensaje
            message_params = {
                "to": recipient,
                "body": content.get("body", ""),
            }

            # Usar messaging_service_sid si está configurado
            messaging_service_sid = self._config.get("messaging_service_sid")
            if messaging_service_sid:
                message_params["messaging_service_sid"] = messaging_service_sid
            else:
                message_params["from_"] = from_number

            # Agregar media si existe
            media_url = content.get("media_url")
            if media_url:
                message_params["media_url"] = [media_url] if isinstance(media_url, str) else media_url

            # Enviar mensaje
            message = client.messages.create(**message_params)

            logger.info(f"Mensaje Twilio enviado: {message.sid} a {recipient}")

            return ProviderResponse(
                success=True,
                message_id=message.sid,
                raw_response={
                    "sid": message.sid,
                    "status": message.status,
                    "to": message.to,
                    "from": message.from_,
                }
            )

        except Exception as e:
            return self._handle_error(e, f"Error enviando via Twilio a {recipient}")

    def send_sms(self, to: str, body: str, **kwargs) -> ProviderResponse:
        """Atajo para enviar SMS."""
        return self.send(to, {"body": body}, channel="sms", **kwargs)

    def send_whatsapp(self, to: str, body: str, **kwargs) -> ProviderResponse:
        """Atajo para enviar WhatsApp."""
        return self.send(to, {"body": body}, channel="whatsapp", **kwargs)

    def send_whatsapp_template(
        self,
        to: str,
        template_sid: str,
        template_variables: Dict[str, str],
        **kwargs
    ) -> ProviderResponse:
        """
        Envía un mensaje de WhatsApp usando un template pre-aprobado.

        Args:
            to: Número de teléfono.
            template_sid: SID del template en Twilio.
            template_variables: Variables para el template.
        """
        try:
            client = self.get_client()
            from_number = self._config.get("whatsapp_from")

            if not to.startswith("whatsapp:"):
                to = f"whatsapp:{to}"

            message = client.messages.create(
                to=to,
                from_=from_number,
                content_sid=template_sid,
                content_variables=template_variables,
            )

            return ProviderResponse(
                success=True,
                message_id=message.sid,
            )

        except Exception as e:
            return self._handle_error(e, f"Error enviando WhatsApp template a {to}")
