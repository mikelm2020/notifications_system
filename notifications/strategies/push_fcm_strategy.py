# ============================================================================
# PUSH FCM STRATEGY
# ============================================================================

"""
push_fcm_strategy.py - Estrategia para Push Notifications via FCM.
"""

import logging
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from notifications.models import DeviceToken, Notification, PushTemplate
from notifications.providers.fcm import FCMProvider
from notifications.strategies.base_strategy import NotificationChannelStrategy

logger = logging.getLogger(__name__)


@dataclass
class PushContent:
    """Contenido para notificación Push."""

    title: str
    body: str
    icon: Optional[str] = None
    image: Optional[str] = None
    click_action: Optional[str] = None
    data: Optional[Dict[str, Any]] = None


class PushFCMChannelStrategy(NotificationChannelStrategy):
    """Estrategia para Push Notifications usando Firebase Cloud Messaging."""

    channel_name = "push_fcm"
    provider_class = FCMProvider

    def prepare_content(self, template: PushTemplate, context: Dict[str, Any]) -> PushContent:
        """
        Prepara el contenido del Push.

        Args:
            template: Modelo PushTemplate.
            context: Variables de contexto.

        Returns:
            PushContent con título, cuerpo, etc.
        """
        title = self.render_template_string(template.title, context)
        body = self.render_template_string(template.body, context)

        click_action = None
        if template.click_action:
            click_action = self.render_template_string(template.click_action, context)

        # Combinar data del template con data del contexto
        data = template.data.copy() if template.data else {}
        if context.get("push_data"):
            data.update(context["push_data"])

        return PushContent(
            title=title,
            body=body,
            icon=template.icon or None,
            image=template.image or None,
            click_action=click_action,
            data=data or None,
        )

    def get_device_tokens(self, notification: Notification) -> List[str]:
        """
        Obtiene los tokens FCM del usuario.

        Args:
            notification: Modelo Notification.

        Returns:
            Lista de tokens FCM activos.
        """
        if not notification.user_id:
            return []

        tokens = DeviceToken.objects.filter(
            user=notification.user_id,
            platform__in=["android", "ios"],
            is_active=True,
        ).values_list("token", flat=True)

        return list(tokens)

    def send(self, notification: Notification, content: PushContent) -> bool:
        """
        Envía la notificación Push a todos los dispositivos del usuario.

        Args:
            notification: Modelo Notification.
            content: PushContent preparado.

        Returns:
            True si al menos un envío fue exitoso.
        """
        try:
            provider = self.provider
            tokens = self.get_device_tokens(notification)

            if not tokens:
                logger.warning(
                    f"No hay tokens FCM para usuario {notification.user_id} "
                    f"(notificación {notification.uuid})"
                )
                notification.error_message = "No hay dispositivos registrados"
                return False

            push_content = {
                "title": content.title,
                "body": content.body,
                "image": content.image,
                "data": content.data,
            }

            # Enviar a todos los dispositivos
            if len(tokens) == 1:
                response = provider.send(tokens[0], push_content)
                success = response.success
                if response.success:
                    notification.external_id = response.message_id
                else:
                    self.update_notification_from_response(notification, response)
                    # Desactivar token si es inválido
                    if response.error_code in ["INVALID_TOKEN", "UNREGISTERED"]:
                        self._deactivate_token(tokens[0])
            else:
                # Multicast para múltiples dispositivos
                results = provider.send_multicast(tokens, push_content)
                success_count = sum(1 for r in results.values() if r.success)
                success = success_count > 0

                if not success:
                    for result in results.values():
                        self.update_notification_from_response(notification, result)
                        if result.error_code == "DELIVERY_UNKNOWN":
                            break

                # Desactivar tokens inválidos
                for token, result in results.items():
                    if result.error_code in ["INVALID_TOKEN", "UNREGISTERED"]:
                        self._deactivate_token(token)

                notification.external_id = f"multicast_{success_count}/{len(tokens)}"

            self.log_send_result(notification, success)

            # Guardar contenido renderizado
            notification.rendered_content = {
                "title": content.title,
                "body": content.body,
                "devices_count": len(tokens),
            }

            return success

        except Exception as e:
            logger.error(f"Error enviando Push FCM {notification.uuid}: {str(e)}")
            self.record_send_error(notification, e)
            return False

    def _deactivate_token(self, token: str):
        """Desactiva un token FCM inválido."""
        try:
            DeviceToken.objects.filter(token=token).update(is_active=False)
            logger.info(f"Token FCM desactivado: {token[:20]}...")
        except Exception as e:
            logger.warning(f"Error desactivando token: {e}")
