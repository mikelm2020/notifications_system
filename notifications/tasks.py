# ============================================================================
# CELERY TASKS
# ============================================================================

"""
tasks.py - Tareas asíncronas para envío de notificaciones.
"""

import logging
import uuid
from datetime import timedelta
from typing import Dict, List, Optional

from celery import Task, shared_task
from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from notifications.conf import notifications_config
from notifications.exceptions import AMBIGUOUS_DELIVERY_CODES, ChannelSendError
from notifications.models import Notification

logger = logging.getLogger(__name__)


class CommittedCreationTask(Task):
    """Do not publish unpersisted business intent from an open transaction."""

    def apply_async(self, args=None, kwargs=None, **options):
        connection = transaction.get_connection()
        if connection.in_atomic_block or not connection.get_autocommit():
            raise RuntimeError(
                "Use AsyncNotificationService inside business transactions to persist intent"
            )
        return super().apply_async(args=args, kwargs=kwargs, **options)


def _delivery_uuid(task_id):
    return str(uuid.uuid5(uuid.NAMESPACE_URL, task_id)) if task_id else str(uuid.uuid4())


@shared_task(
    bind=True,
    base=CommittedCreationTask,
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

    notification_data_dict = dict(notification_data_dict)
    if not notification_data_dict.get("uuid"):
        notification_data_dict["uuid"] = _delivery_uuid(self.request.id)
    exhausted = False
    notifications = []
    service = None
    try:
        notification_data = NotificationData(**notification_data_dict)
        service = NotificationService()

        notifications = service.create_and_send_notification(notification_data)

        failed = [
            n
            for n in notifications
            if n.status == Notification.Status.FAILED
            and n.error_code not in AMBIGUOUS_DELIVERY_CODES
        ]
        if failed:
            exhausted = all(
                n.failed_permanently_at is not None or n.retry_count >= max_retries for n in failed
            )
            raise ChannelSendError(
                failed[0].channel_id.name, failed[0].error_message or "Send failed"
            )

        return {
            "success": bool(notifications)
            and all(
                n.status
                in (
                    Notification.Status.SENT,
                    Notification.Status.DELIVERED,
                    Notification.Status.READ,
                )
                for n in notifications
            ),
            "notification_ids": [str(n.uuid) for n in notifications],
            "channels": [n.channel_id.name for n in notifications],
        }

    except Exception as exc:
        logger.error(f"Error en tarea de notificación: {str(exc)}")

        if self.request.retries < max_retries and not exhausted:
            raise self.retry(
                exc=exc,
                countdown=retry_delay,
                max_retries=max_retries,
                args=(),
                kwargs={"notification_data_dict": notification_data_dict},
            )
        else:
            if service is not None:
                for notification in notifications:
                    if notification.status == Notification.Status.FAILED:
                        service.finalize_failure(notification, notification_data_dict)
            raise


@shared_task(bind=True, base=CommittedCreationTask)
def send_to_channel_async(
    self,
    event_code: str,
    user_id: int,
    channel: str,
    context: Dict,
    recipient: Optional[str] = None,
    delivery_uuid: Optional[str] = None,
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
            uuid=delivery_uuid or _delivery_uuid(self.request.id),
        )

        service = NotificationService()
        notifications = service.create_and_send_notification(
            notification_data,
            channels=[channel],
        )

        return {
            "success": bool(notifications)
            and all(
                n.status
                in (
                    Notification.Status.SENT,
                    Notification.Status.DELIVERED,
                    Notification.Status.READ,
                )
                for n in notifications
            ),
            "notification_id": str(notifications[0].uuid) if notifications else None,
        }

    except Exception as e:
        logger.error(f"Error enviando por canal {channel}: {str(e)}")
        return {"success": False, "error": str(e)}


@shared_task(bind=True, base=CommittedCreationTask)
def send_email_async(
    self,
    event_code: str,
    user_id: int,
    user_email: str,
    context: Dict,
):
    """Tarea asíncrona específica para emails."""
    context["user_email"] = user_email
    return send_to_channel_async(
        event_code,
        user_id,
        "email",
        context,
        user_email,
        delivery_uuid=_delivery_uuid(self.request.id),
    )


@shared_task(bind=True, base=CommittedCreationTask)
def send_sms_async(
    self,
    event_code: str,
    user_id: int,
    phone_number: str,
    context: Dict,
):
    """Tarea asíncrona específica para SMS."""
    context["phone_number"] = phone_number
    return send_to_channel_async(
        event_code,
        user_id,
        "sms",
        context,
        phone_number,
        delivery_uuid=_delivery_uuid(self.request.id),
    )


@shared_task(bind=True, base=CommittedCreationTask)
def send_push_async(
    self,
    event_code: str,
    user_id: int,
    context: Dict,
):
    """Tarea asíncrona para Push (FCM)."""
    return send_to_channel_async(
        event_code, user_id, "push_fcm", context, delivery_uuid=_delivery_uuid(self.request.id)
    )


@shared_task(bind=True, base=CommittedCreationTask)
def send_whatsapp_async(
    self,
    event_code: str,
    user_id: int,
    phone_number: str,
    context: Dict,
):
    """Tarea asíncrona para WhatsApp."""
    context["phone_number"] = phone_number
    return send_to_channel_async(
        event_code,
        user_id,
        "whatsapp",
        context,
        phone_number,
        delivery_uuid=_delivery_uuid(self.request.id),
    )


# ============================================================================
# PERIODIC TASKS
# ============================================================================


@shared_task
def retry_failed_notifications():
    """
    Tarea periódica para reintentar notificaciones fallidas.
    Ejecutar con Celery Beat cada X minutos.
    """
    from notifications.services.notification_service import NotificationService

    max_retry_count = notifications_config.max_retries
    retry_window = timezone.now() - timedelta(hours=24)

    failed_notifications = (
        Notification.objects.filter(
            status=Notification.Status.FAILED,
            failed_permanently_at__isnull=True,
            retry_count__lt=max_retry_count,
            created_at__gte=retry_window,
            updated_at__lte=timezone.now() - timedelta(seconds=notifications_config.retry_delay),
        )
        .exclude(error_code__in=AMBIGUOUS_DELIVERY_CODES)
        .select_related("notification_type_id", "channel_id")
    )

    service = NotificationService()
    success_count = 0
    failed_count = 0
    processed = 0

    for notification in failed_notifications:
        try:
            context = notification.context_data or {}
            if not service._send_notification(notification, context):
                continue
            processed += 1

            if notification.status in (
                Notification.Status.SENT,
                Notification.Status.DELIVERED,
                Notification.Status.READ,
            ):
                success_count += 1
            else:
                failed_count += 1

        except Exception as e:
            logger.error(f"Error reintentando notificación {notification.uuid}: {str(e)}")
            failed_count += 1

    logger.info(f"Reintento de notificaciones: {success_count} exitosas, {failed_count} fallidas")

    return {
        "processed": processed,
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
        status__in=[Notification.Status.PENDING, Notification.Status.QUEUED],
        scheduled_for__lte=now,
        scheduled_for__isnull=False,
    ).select_related("notification_type_id", "channel_id")

    service = NotificationService()
    processed = 0

    for notification in scheduled_notifications:
        try:
            context = notification.context_data or {}
            if service._send_notification(notification, context):
                processed += 1
        except Exception as e:
            logger.error(f"Error procesando notificación programada {notification.uuid}: {str(e)}")

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

    logger.info(f"Limpieza: {deleted_count} notificaciones y {logs_deleted} logs eliminados")

    return {
        "notifications_deleted": deleted_count,
        "logs_deleted": logs_deleted,
    }


@shared_task(bind=True, base=CommittedCreationTask)
def send_batch_notifications(self, notification_data_list: List[Dict]):
    """
    Tarea para enviar notificaciones en batch.

    Args:
        notification_data_list: Lista de diccionarios con datos de NotificationData.
    """
    from notifications.dtos.notification_data import NotificationData
    from notifications.services.notification_service import NotificationService

    service = NotificationService()
    results = {"success": 0, "failed": 0, "errors": []}

    batch_uuid = _delivery_uuid(self.request.id)
    for index, data_dict in enumerate(notification_data_list):
        try:
            data_dict = dict(data_dict)
            if not data_dict.get("uuid"):
                data_dict["uuid"] = str(uuid.uuid5(uuid.UUID(batch_uuid), str(index)))
            notification_data = NotificationData(**data_dict)
            notifications = service.create_and_send_notification(notification_data)
            if not notifications or any(
                n.status
                not in (
                    Notification.Status.SENT,
                    Notification.Status.DELIVERED,
                    Notification.Status.READ,
                )
                for n in notifications
            ):
                raise ChannelSendError("batch", "Notification delivery not confirmed")
            results["success"] += 1
        except Exception as e:
            results["failed"] += 1
            results["errors"].append(
                {
                    "data": data_dict,
                    "error": str(e),
                }
            )

    logger.info(f"Batch: {results['success']} exitosas, {results['failed']} fallidas")

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


@shared_task
def dispatch_notification(notification_id):
    """Deliver a persisted intent using the same atomic claim as recovery."""
    from notifications.services.notification_service import NotificationService

    notification = (
        Notification.objects.filter(pk=notification_id)
        .select_related("notification_type_id", "channel_id")
        .first()
    )
    if notification is None:
        return False
    return NotificationService()._send_notification(notification, notification.context_data)


@shared_task
def recover_queued_notifications():
    """Scan committed intents; provider I/O happens without locks or transactions."""
    ids = Notification.objects.filter(
        status=Notification.Status.QUEUED,
        failed_permanently_at__isnull=True,
    ).filter(Q(scheduled_for__isnull=True) | Q(scheduled_for__lte=timezone.now()))
    processed = 0
    for pk in ids.values_list("pk", flat=True).iterator(chunk_size=100):
        try:
            processed += bool(dispatch_notification.run(pk))
        except Exception:
            logger.exception("Recovery failed for notification %s", pk)
    return {"processed": processed}
