# ============================================================================
# SMTP PROVIDER
# ============================================================================

"""
smtp.py - Proveedor para envío de emails via SMTP.

Usa la configuración de email de Django por defecto.
"""

import logging
from typing import Any, Dict, Optional

from django.conf import settings
from django.core.mail import EmailMultiAlternatives, get_connection

from notifications.providers.base import BaseProvider, ProviderResponse

logger = logging.getLogger(__name__)


class SMTPProvider(BaseProvider):
    """
    Proveedor de email usando SMTP de Django.

    Configuración en NOTIFICATIONS_CONFIG:
        "smtp": {
            "use_django_settings": True,  # Usa EMAIL_* de Django
            # O especifica directamente:
            "host": "smtp.gmail.com",
            "port": 587,
            "username": "...",
            "password": "...",
            "use_tls": True,
            "use_ssl": False,
            "from_email": "noreply@example.com",
        }
    """

    provider_name = "smtp"
    required_config_fields = []  # Puede usar config de Django

    def get_client(self) -> Any:
        """Obtiene una conexión SMTP."""
        if self._config.get("use_django_settings", True):
            return get_connection()

        return get_connection(
            host=self._config.get("host", settings.EMAIL_HOST),
            port=self._config.get("port", settings.EMAIL_PORT),
            username=self._config.get("username", settings.EMAIL_HOST_USER),
            password=self._config.get("password", settings.EMAIL_HOST_PASSWORD),
            use_tls=self._config.get("use_tls", settings.EMAIL_USE_TLS),
            use_ssl=self._config.get("use_ssl", getattr(settings, "EMAIL_USE_SSL", False)),
        )

    def send(
        self,
        recipient: str,
        content: Dict[str, Any],
        **kwargs
    ) -> ProviderResponse:
        """
        Envía un email.

        Args:
            recipient: Email del destinatario.
            content: Dict con:
                - subject: Asunto del email
                - body: Cuerpo texto plano
                - html_body: Cuerpo HTML (opcional)
            **kwargs:
                - from_email: Remitente (opcional)
                - cc: Lista de CC (opcional)
                - bcc: Lista de BCC (opcional)
                - reply_to: Lista de Reply-To (opcional)
                - attachments: Lista de adjuntos (opcional)

        Returns:
            ProviderResponse con resultado.
        """
        try:
            from_email = kwargs.get(
                "from_email",
                self._config.get("from_email", settings.DEFAULT_FROM_EMAIL)
            )

            email = EmailMultiAlternatives(
                subject=content.get("subject", ""),
                body=content.get("body", ""),
                from_email=from_email,
                to=[recipient],
                cc=kwargs.get("cc"),
                bcc=kwargs.get("bcc"),
                reply_to=kwargs.get("reply_to"),
            )

            # Agregar versión HTML si existe
            html_body = content.get("html_body")
            if html_body:
                email.attach_alternative(html_body, "text/html")

            # Agregar adjuntos
            attachments = kwargs.get("attachments", [])
            for attachment in attachments:
                if isinstance(attachment, tuple):
                    email.attach(*attachment)
                else:
                    email.attach_file(attachment)

            # Enviar
            connection = self.get_client()
            sent = email.send(fail_silently=False)

            if sent:
                logger.info(f"Email enviado a {recipient}")
                return ProviderResponse(
                    success=True,
                    message_id=email.message().get("Message-ID", ""),
                )
            else:
                return ProviderResponse(
                    success=False,
                    error_message="El email no fue enviado",
                )

        except Exception as e:
            return self._handle_error(e, f"Error enviando email a {recipient}")
