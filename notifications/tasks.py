# ============================================================================
# CELERY TASKS
# ============================================================================

"""
tasks.py - Tareas asíncronas para envío de notificaciones.
"""

import logging
from datetime import timedelta
from typing import Dict, List, Optional

from celery import shared_task
from django.utils import timezone

from notifications.conf import notifications_config
from notifications.models import Notification

logger = logging.getLogger(__name__)


@shared_task(
    bind=True,
    max_retries=None,  # Usamos configuración
    default_retry_delay=None,
)
def send_notification_async(self, notification_data_dict: Dict):
    """
    Tarea asíncrona principal para enviar notificaciones.

    Args:
        notification_data_dict: Diccionario con datos de NotificationData.
    """
    from notifications.dtos.notification_data import NotificationData
    from notifications.services.notification_service import NotificationService

    max_retries = notifications_config.max_retries
    retry_delay = notifications_config.retry_delay

    try:
        notification_data = NotificationData(**notification_data_dict)
        service = NotificationService()

        notifications = service.create_and_send_notification(notification_data)

        return {
            "success": True,
            "notification_ids": [str(n.uuid) for n in notifications],
            "channels": [n.channel_id.name for n in notifications],
        }

    except Exception as exc:
        logger.error(f"Error en tarea de notificación: {str(exc)}")

        if self.request.retries < max_retries:
            raise self.retry(exc=exc, countdown=retry_delay)
        else:
            # Emitir signal de fallo permanente
            from notifications.signals import notification_failed_permanently
            notification_failed_permanently.send(
                sender=self.__class__,
                notification_data=notification_data_dict,
                error=exc,
            )
            raise


@shared_task
def send_to_channel_async(
    event_code: str,
    user_id: int,
    channel: str,
    context: Dict,
    recipient: Optional[str] = None,
):
    """
    Tarea asíncrona para enviar por un canal específico.

    Args:
        event_code: Código del evento.
        user_id: ID del usuario.
        channel: Nombre del canal.
        context: Contexto para el template.
        recipient: Identificador del destinatario (opcional).
    """
    from notifications.dtos.notification_data import NotificationData
    from notifications.services.notification_service import NotificationService

    try:
        if recipient:
            context["recipient"] = recipient

        notification_data = NotificationData(
            event_code=event_code,
            user_id=user_id,
            context=context,
        )

        service = NotificationService()
        notifications = service.create_and_send_notification(
            notification_data,
            channels=[channel],
        )

        return {
            "success": True,
            "notification_id": str(notifications[0].uuid) if notifications else None,
        }

    except Exception as e:
        logger.error(f"Error enviando por canal {channel}: {str(e)}")
        return {"success": False, "error": str(e)}


@shared_task
def send_email_async(
    event_code: str,
    user_id: int,
    user_email: str,
    context: Dict,
):
    """Tarea asíncrona específica para emails."""
    context["user_email"] = user_email
    return send_to_channel_async(event_code, user_id, "email", context, user_email)


@shared_task
def send_sms_async(
    event_code: str,
    user_id: int,
    phone_number: str,
    context: Dict,
):
    """Tarea asíncrona específica para SMS."""
    context["phone_number"] = phone_number
    return send_to_channel_async(event_code, user_id, "sms", context, phone_number)


@shared_task
def send_push_async(
    event_code: str,
    user_id: int,
    context: Dict,
):
    """Tarea asíncrona para Push (FCM)."""
    return send_to_channel_async(event_code, user_id, "push_fcm", context)


@shared_task
def send_whatsapp_async(
    event_code: str,
    user_id: int,
    phone_number: str,
    context: Dict,
):
    """Tarea asíncrona para WhatsApp."""
    context["phone_number"] = phone_number
    return send_to_channel_async(event_code, user_id, "whatsapp", context, phone_number)


# ============================================================================
# PERIODIC TASKS
# ============================================================================

@shared_task
def retry_failed_notifications():
    """
    Tarea periódica para reintentar notificaciones fallidas.
    Ejecutar con Celery Beat cada X minutos.
    """
    from notifications.repositories.notification_repository import NotificationRepository
    from notifications.services.notification_service import NotificationService

    max_retry_count = notifications_config.max_retries
    retry_window = timezone.now() - timedelta(hours=24)

    failed_notifications = Notification.objects.filter(
        status=Notification.Status.FAILED,
        retry_count__lt=max_retry_count,
        created_at__gte=retry_window,
    ).select_related("notification_type_id", "channel_id")

    service = NotificationService()
    success_count = 0
    failed_count = 0

    for notification in failed_notifications:
        try:
            # Incrementar contador de reintentos
            notification.retry_count += 1
            notification.status = Notification.Status.PENDING
            notification.save(update_fields=["retry_count", "status", "updated_at"])

            # Intentar reenviar
            context = notification.context_data or {}
            service._send_notification(notification, context)

            if notification.status == Notification.Status.SENT:
                success_count += 1
            else:
                failed_count += 1

        except Exception as e:
            logger.error(
                f"Error reintentando notificación {notification.uuid}: {str(e)}"
            )
            failed_count += 1

    logger.info(
        f"Reintento de notificaciones: {success_count} exitosas, {failed_count} fallidas"
    )

    return {
        "processed": failed_notifications.count(),
        "success": success_count,
        "failed": failed_count,
    }


@shared_task
def process_scheduled_notifications():
    """
    Tarea periódica para enviar notificaciones programadas.
    Ejecutar con Celery Beat cada minuto.
    """
    from notifications.services.notification_service import NotificationService

    now = timezone.now()

    scheduled_notifications = Notification.objects.filter(
        status=Notification.Status.PENDING,
        scheduled_for__lte=now,
        scheduled_for__isnull=False,
    ).select_related("notification_type_id", "channel_id")

    service = NotificationService()
    processed = 0

    for notification in scheduled_notifications:
        try:
            context = notification.context_data or {}
            service._send_notification(notification, context)
            processed += 1
        except Exception as e:
            logger.error(
                f"Error procesando notificación programada {notification.uuid}: {str(e)}"
            )

    if processed:
        logger.info(f"Procesadas {processed} notificaciones programadas")

    return {"processed": processed}


@shared_task
def cleanup_old_notifications():
    """
    Tarea periódica para limpiar notificaciones antiguas.
    Ejecutar con Celery Beat diariamente.
    """
    days = notifications_config.cleanup_after_days
    cutoff_date = timezone.now() - timedelta(days=days)

    # Eliminar notificaciones leídas antiguas
    deleted_count, _ = Notification.objects.filter(
        is_read=True,
        created_at__lt=cutoff_date,
    ).delete()

    # Eliminar logs antiguos
    from notifications.models import NotificationLog
    logs_deleted, _ = NotificationLog.objects.filter(
        timestamp__lt=cutoff_date,
    ).delete()

    logger.info(
        f"Limpieza: {deleted_count} notificaciones y {logs_deleted} logs eliminados"
    )

    return {
        "notifications_deleted": deleted_count,
        "logs_deleted": logs_deleted,
    }


@shared_task
def send_batch_notifications(notification_data_list: List[Dict]):
    """
    Tarea para enviar notificaciones en batch.

    Args:
        notification_data_list: Lista de diccionarios con datos de NotificationData.
    """
    from notifications.dtos.notification_data import NotificationData
    from notifications.services.notification_service import NotificationService

    service = NotificationService()
    results = {"success": 0, "failed": 0, "errors": []}

    for data_dict in notification_data_list:
        try:
            notification_data = NotificationData(**data_dict)
            service.create_and_send_notification(notification_data)
            results["success"] += 1
        except Exception as e:
            results["failed"] += 1
            results["errors"].append({
                "data": data_dict,
                "error": str(e),
            })

    logger.info(
        f"Batch: {results['success']} exitosas, {results['failed']} fallidas"
    )

    return results


@shared_task
def deactivate_expired_device_tokens():
    """
    Tarea periódica para desactivar tokens de dispositivos no usados.
    Ejecutar con Celery Beat semanalmente.
    """
    from notifications.models import DeviceToken

    # Desactivar tokens no usados en 90 días
    cutoff_date = timezone.now() - timedelta(days=90)

    count = DeviceToken.objects.filter(
        is_active=True,
        last_used_at__lt=cutoff_date,
    ).update(is_active=False)

    # También desactivar tokens que nunca fueron usados y tienen más de 30 días
    old_unused = timezone.now() - timedelta(days=30)
    count += DeviceToken.objects.filter(
        is_active=True,
        last_used_at__isnull=True,
        created_at__lt=old_unused,
    ).update(is_active=False)

    logger.info(f"Desactivados {count} tokens de dispositivo expirados")

    return {"deactivated": count}
