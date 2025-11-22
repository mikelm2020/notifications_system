# ============================================================================
# WEBHOOK STRATEGY
# ============================================================================

"""
webhook_strategy.py - Estrategia para notificaciones via Webhook.
"""

import json
import logging
from dataclasses import dataclass
from typing import Any, Dict, Optional

import httpx

from notifications.models import Notification, WebhookTemplate
from notifications.strategies.base_strategy import NotificationChannelStrategy

logger = logging.getLogger(__name__)


@dataclass
class WebhookContent:
    """Contenido para notificación Webhook."""
    url: str
    method: str
    headers: Dict[str, str]
    payload: Dict[str, Any]
    timeout: int


class WebhookChannelStrategy(NotificationChannelStrategy):
    """
    Estrategia para envío de notificaciones via Webhook.

    Permite integrar con sistemas externos mediante HTTP callbacks.
    """

    channel_name = "webhook"
    provider_class = None  # Usa httpx directamente

    def prepare_content(
        self,
        template: WebhookTemplate,
        context: Dict[str, Any]
    ) -> WebhookContent:
        """
        Prepara el contenido del Webhook.

        Args:
            template: Modelo WebhookTemplate.
            context: Variables de contexto.

        Returns:
            WebhookContent con URL, payload, etc.
        """
        # Renderizar URL con variables
        url = self.render_template_string(template.url, context)

        # Renderizar payload
        payload_str = self.render_template_string(template.payload_template, context)
        try:
            payload = json.loads(payload_str)
        except json.JSONDecodeError:
            logger.warning(f"Payload no es JSON válido, usando como string")
            payload = {"data": payload_str}

        # Renderizar headers
        headers = {"Content-Type": "application/json"}
        if template.headers:
            for key, value in template.headers.items():
                headers[key] = self.render_template_string(str(value), context)

        return WebhookContent(
            url=url,
            method=template.method,
            headers=headers,
            payload=payload,
            timeout=template.timeout,
        )

    def send(self, notification: Notification, content: WebhookContent) -> bool:
        """
        Envía la petición HTTP al webhook.

        Args:
            notification: Modelo Notification.
            content: WebhookContent preparado.

        Returns:
            True si la respuesta es 2xx.
        """
        try:
            # Agregar metadata de la notificación al payload
            payload = content.payload.copy()
            payload["_notification"] = {
                "uuid": str(notification.uuid),
                "type": notification.notification_type_id.event_code,
                "timestamp": notification.created_at.isoformat(),
            }

            with httpx.Client(timeout=content.timeout) as client:
                if content.method == "POST":
                    response = client.post(
                        content.url,
                        json=payload,
                        headers=content.headers,
                    )
                elif content.method == "PUT":
                    response = client.put(
                        content.url,
                        json=payload,
                        headers=content.headers,
                    )
                elif content.method == "PATCH":
                    response = client.patch(
                        content.url,
                        json=payload,
                        headers=content.headers,
                    )
                else:
                    logger.error(f"Método HTTP no soportado: {content.method}")
                    return False

            success = 200 <= response.status_code < 300

            if success:
                logger.info(
                    f"Webhook enviado exitosamente a {content.url}: "
                    f"status={response.status_code}"
                )
                notification.external_id = f"http_{response.status_code}"
            else:
                logger.error(
                    f"Webhook falló: {content.url} - "
                    f"status={response.status_code}, body={response.text[:200]}"
                )
                notification.error_message = f"HTTP {response.status_code}: {response.text[:200]}"
                notification.error_code = str(response.status_code)

            # Guardar contenido para auditoría
            notification.rendered_content = {
                "url": content.url,
                "method": content.method,
                "status_code": response.status_code,
                "payload_preview": str(payload)[:500],
            }
            notification.recipient_identifier = content.url

            return success

        except httpx.TimeoutException:
            logger.error(f"Timeout en webhook {content.url} después de {content.timeout}s")
            notification.error_message = f"Timeout después de {content.timeout} segundos"
            notification.error_code = "TIMEOUT"
            return False

        except httpx.ConnectError as e:
            logger.error(f"Error de conexión al webhook {content.url}: {e}")
            notification.error_message = f"Error de conexión: {str(e)}"
            notification.error_code = "CONNECTION_ERROR"
            return False

        except Exception as e:
            logger.error(f"Error enviando webhook {notification.uuid}: {str(e)}")
            notification.error_message = str(e)
            return False
