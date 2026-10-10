# ============================================================================
# PUSH WEB STRATEGY
# ============================================================================

"""
push_web_strategy.py - Estrategia para Web Push Notifications.
"""

import logging
from typing import Any, Dict, List

from notifications.models import DeviceToken, Notification, PushTemplate
from notifications.providers.webpush import WebPushProvider
from notifications.strategies.base_strategy import NotificationChannelStrategy
from notifications.strategies.push_fcm_strategy import PushContent

logger = logging.getLogger(__name__)


class PushWebChannelStrategy(NotificationChannelStrategy):
    """Estrategia para Web Push Notifications."""

    channel_name = "push_web"
    provider_class = WebPushProvider

    def prepare_content(self, template: PushTemplate, context: Dict[str, Any]) -> PushContent:
        """
        Prepara el contenido del Web Push.

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

    def get_subscriptions(self, notification: Notification) -> List[Dict]:
        """
        Obtiene las subscripciones Web Push del usuario.

        Args:
            notification: Modelo Notification.

        Returns:
            Lista de subscription info dicts.
        """
        if not notification.user_id:
            return []

        tokens = DeviceToken.objects.filter(
            user=notification.user_id,
            platform="web",
            is_active=True,
        )

        subscriptions = []
        for token in tokens:
            if token.endpoint and token.p256dh_key and token.auth_key:
                subscriptions.append(
                    {
                        "endpoint": token.endpoint,
                        "keys": {
                            "p256dh": token.p256dh_key,
                            "auth": token.auth_key,
                        },
                    }
                )

        return subscriptions

    def send(self, notification: Notification, content: PushContent) -> bool:
        """
        Envía la notificación Web Push a todos los navegadores del usuario.

        Args:
            notification: Modelo Notification.
            content: PushContent preparado.

        Returns:
            True si al menos un envío fue exitoso.
        """
        try:
            provider = self.provider
            subscriptions = self.get_subscriptions(notification)

            if not subscriptions:
                logger.warning(
                    f"No hay subscripciones Web Push para usuario {notification.user_id} "
                    f"(notificación {notification.uuid})"
                )
                notification.error_message = "No hay navegadores registrados"
                return False

            push_content = {
                "title": content.title,
                "body": content.body,
                "icon": content.icon,
                "badge": content.icon,  # Usar icono como badge
                "image": content.image,
                "data": {
                    **(content.data or {}),
                    "url": content.click_action,
                    "notification_uuid": str(notification.uuid),
                },
                "tag": str(notification.uuid),  # Para agrupar/reemplazar
            }

            success_count = 0
            for subscription in subscriptions:
                response = provider.send(subscription, push_content)
                if response.success:
                    success_count += 1
                else:
                    if notification.error_code != "DELIVERY_UNKNOWN":
                        self.update_notification_from_response(notification, response)
                    # Desactivar subscription si expiró
                    if response.error_code in ["SUBSCRIPTION_EXPIRED", "SUBSCRIPTION_NOT_FOUND"]:
                        self._deactivate_subscription(subscription["endpoint"])

            success = success_count > 0
            self.log_send_result(notification, success)

            notification.rendered_content = {
                "title": content.title,
                "body": content.body,
                "subscriptions_count": len(subscriptions),
                "success_count": success_count,
            }
            notification.external_id = f"webpush_{success_count}/{len(subscriptions)}"

            return success

        except Exception as e:
            logger.error(f"Error enviando Web Push {notification.uuid}: {str(e)}")
            self.record_send_error(notification, e)
            return False

    def _deactivate_subscription(self, endpoint: str):
        """Desactiva una subscription expirada."""
        try:
            DeviceToken.objects.filter(endpoint=endpoint).update(is_active=False)
            logger.info(f"Subscription Web Push desactivada: {endpoint[:50]}...")
        except Exception as e:
            logger.warning(f"Error desactivando subscription: {e}")
