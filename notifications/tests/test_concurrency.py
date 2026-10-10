from concurrent.futures import ThreadPoolExecutor
from threading import Event
from unittest.mock import Mock, patch

from django.db import close_old_connections
from django.test import TransactionTestCase

from notifications.models import (
    Notification,
    NotificationCategory,
    NotificationChannel,
    NotificationType,
)
from notifications.services.notification_service import NotificationService


class ConcurrentDeliveryTests(TransactionTestCase):
    def test_two_workers_overlapping_delivery_call_provider_once(self):
        category = NotificationCategory.objects.create(name="concurrent")
        kind = NotificationType.objects.create(category_id=category, event_code="CONCURRENT")
        channel = NotificationChannel.objects.create(name="email")
        n = Notification.objects.create(notification_type_id=kind, channel_id=channel)
        entered = Event()
        release = Event()
        strategy = Mock()

        def send(*args):
            entered.set()
            if not release.wait(5):
                raise RuntimeError("test worker timed out")
            return True

        strategy.send.side_effect = send

        def worker():
            close_old_connections()
            try:
                record = Notification.objects.get(pk=n.pk)
                return NotificationService()._send_notification(record, {})
            finally:
                close_old_connections()

        with (
            patch(
                "notifications.factories.channel_factory.NotificationChannelFactory.create",
                return_value=strategy,
            ),
            patch.object(NotificationService, "_get_template_for_channel", return_value=Mock()),
            ThreadPoolExecutor(max_workers=2) as pool,
        ):
            first = pool.submit(worker)
            try:
                self.assertTrue(entered.wait(5))
                self.assertFalse(pool.submit(worker).result(timeout=5))
            finally:
                release.set()
            self.assertTrue(first.result(timeout=5))
        strategy.send.assert_called_once()
        n.refresh_from_db()
        self.assertEqual(n.status, Notification.Status.SENT)
