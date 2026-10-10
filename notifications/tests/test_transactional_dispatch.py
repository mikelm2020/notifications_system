from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from threading import Event
from unittest.mock import patch

from django.db import close_old_connections, connection, transaction
from django.test import TransactionTestCase
from django.utils import timezone

from notifications.dtos.notification_data import NotificationData
from notifications.models import Notification
from notifications.services.async_service import AsyncNotificationService
from notifications.services.notification_service import NotificationService
from notifications.tasks import (
    dispatch_notification,
    recover_queued_notifications,
    send_notification_async,
)
from notifications.tests import test_post_audit


class TransactionalDispatchTests(TransactionTestCase):
    setUp = test_post_audit.PostAuditTests.setUp
    notification = test_post_audit.PostAuditTests.notification

    def test_commit_defers_provider_and_persists_intent(self):
        def send(*args):
            self.assertFalse(connection.in_atomic_block)
            self.assertTrue(connection.get_autocommit())
            return True

        self.strategy.send.side_effect = send
        with transaction.atomic():
            n = NotificationService().create_and_send_notification(NotificationData(**self.data))[0]
            self.assertEqual(n.status, Notification.Status.QUEUED)
            self.strategy.send.assert_not_called()
        n.refresh_from_db()
        self.assertEqual(n.status, Notification.Status.SENT)
        self.strategy.send.assert_called_once()

    def test_broker_failure_remains_recoverable(self):
        with patch.object(dispatch_notification, "delay", side_effect=ConnectionError("broker")):
            with transaction.atomic():
                n = NotificationService().create_and_send_notification(
                    NotificationData(**self.data)
                )[0]
        n.refresh_from_db()
        self.assertEqual(n.status, Notification.Status.QUEUED)
        self.strategy.send.assert_not_called()
        self.assertEqual(recover_queued_notifications.run(), {"processed": 1})
        self.assertFalse(dispatch_notification.run(n.pk))
        self.assertEqual(recover_queued_notifications.run(), {"processed": 0})
        self.strategy.send.assert_called_once()

    def test_process_loss_before_callback_is_recovered(self):
        with patch("notifications.services.notification_service.transaction.on_commit"):
            n = NotificationService().create_and_send_notification(NotificationData(**self.data))[0]
        self.assertEqual(n.status, Notification.Status.QUEUED)
        self.assertEqual(recover_queued_notifications.run()["processed"], 1)
        self.strategy.send.assert_called_once()

    def test_recovery_excludes_future_and_terminal_records(self):
        for status in (
            Notification.Status.CANCELLED,
            Notification.Status.SENT,
            Notification.Status.SENDING,
            Notification.Status.FAILED,
        ):
            self.notification(status=status)
        self.notification(
            status=Notification.Status.QUEUED, scheduled_for=timezone.now() + timedelta(hours=1)
        )
        self.notification(status=Notification.Status.QUEUED, failed_permanently_at=timezone.now())
        self.assertEqual(recover_queued_notifications.run()["processed"], 0)
        self.strategy.send.assert_not_called()

    def test_async_wrapper_rollback_does_not_publish(self):
        with patch.object(dispatch_notification, "delay") as publish:
            with self.assertRaises(RuntimeError):
                with transaction.atomic():
                    AsyncNotificationService.send_async(NotificationData(**self.data))
                    raise RuntimeError("rollback")
        publish.assert_not_called()
        self.assertFalse(Notification.objects.exists())

    def test_worker_and_recovery_share_claim(self):
        n = self.notification(status=Notification.Status.QUEUED)
        entered, release = Event(), Event()

        def send(*args):
            entered.set()
            if not release.wait(10):
                raise RuntimeError("timeout")
            return True

        self.strategy.send.side_effect = send

        def worker():
            close_old_connections()
            try:
                return dispatch_notification.run(n.pk)
            finally:
                close_old_connections()

        with ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(worker)
            try:
                self.assertTrue(entered.wait(10))
                self.assertEqual(recover_queued_notifications.run()["processed"], 0)
                self.assertFalse(dispatch_notification.run(n.pk))
            finally:
                release.set()
            self.assertTrue(future.result(timeout=10))
        self.strategy.send.assert_called_once()

    def test_raw_creation_task_cannot_publish_unpersisted_intent_in_atomic(self):
        with transaction.atomic():
            with self.assertRaisesRegex(RuntimeError, "AsyncNotificationService"):
                send_notification_async.delay(self.data)
        self.strategy.send.assert_not_called()
        self.assertFalse(Notification.objects.exists())
