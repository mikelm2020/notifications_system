"""Persist asynchronous delivery intent before contacting the broker."""

from notifications.dtos.notification_data import NotificationData
from notifications.services.notification_service import NotificationService


class AsyncNotificationService:
    @staticmethod
    def send_async(notification_data: NotificationData):
        notifications = NotificationService().create_and_send_notification(
            notification_data, enqueue=True
        )
        return str(notifications[0].uuid) if notifications else None

    @staticmethod
    def send_email_async(event_code, user_id, user_email, context):
        data = NotificationData(
            event_code=event_code,
            user_id=user_id,
            context={**context, "user_email": user_email},
        )
        notifications = NotificationService().create_and_send_notification(
            data, channels=["email"], enqueue=True
        )
        return str(notifications[0].uuid) if notifications else None

    @staticmethod
    def schedule_notification(notification_data: NotificationData, send_at):
        notification_data.scheduled_for = send_at
        return AsyncNotificationService.send_async(notification_data)
