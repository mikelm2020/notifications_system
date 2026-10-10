from concurrent.futures import ThreadPoolExecutor
from threading import Barrier, Event
from unittest import skipUnless
from unittest.mock import Mock, patch
from uuid import uuid4

from django.db import close_old_connections, connection, connections, transaction
from django.test import TransactionTestCase

from notifications.models import (
    Notification,
    NotificationCategory,
    NotificationChannel,
    NotificationType,
)
from notifications.repositories.notification_repository import NotificationRepository
from notifications.services.notification_service import NotificationService


@skipUnless(connection.vendor == "postgresql", "Requires isolated PostgreSQL test database")
class PostgreSQLConcurrencyTests(TransactionTestCase):
    def setUp(self):
        category = NotificationCategory.objects.create(name="postgres")
        self.kind = NotificationType.objects.create(category_id=category, event_code="POSTGRES")
        self.channel = NotificationChannel.objects.create(name="email")
        self.n = Notification.objects.create(
            notification_type_id=self.kind, channel_id=self.channel
        )

    def worker(self, action):
        close_old_connections()
        try:
            self.assertFalse(connection.in_atomic_block)
            return action()
        finally:
            connections.close_all()

    def parallel(self, actions):
        with ThreadPoolExecutor(max_workers=len(actions)) as pool:
            futures = [pool.submit(self.worker, action) for action in actions]
            return [f.result(timeout=15) for f in futures]

    def test_simultaneous_pending_claim_has_one_winner(self):
        barrier = Barrier(2)

        def claim():
            n = Notification.objects.get(pk=self.n.pk)
            barrier.wait(timeout=10)
            return NotificationRepository.claim_for_send(n)

        self.assertEqual(sorted(self.parallel([claim, claim])), [False, True])
        self.n.refresh_from_db()
        self.assertEqual(self.n.status, Notification.Status.SENDING)
        self.assertEqual(self.n.retry_count, 0)

    def test_simultaneous_failed_claim_increments_retry_once(self):
        from datetime import timedelta

        from django.utils import timezone

        from notifications.conf import notifications_config

        Notification.objects.filter(pk=self.n.pk).update(
            status=Notification.Status.FAILED,
            updated_at=timezone.now() - timedelta(seconds=notifications_config.retry_delay + 1),
        )
        barrier = Barrier(2)

        def claim():
            n = Notification.objects.get(pk=self.n.pk)
            barrier.wait(timeout=10)
            return NotificationRepository.claim_for_send(n)

        self.assertEqual(sorted(self.parallel([claim, claim])), [False, True])
        self.n.refresh_from_db()
        self.assertEqual(self.n.retry_count, 1)

    def test_simultaneous_creation_uses_unique_constraint(self):
        delivery_uuid = str(uuid4())
        barrier = Barrier(2)

        def create():
            barrier.wait(timeout=10)
            return NotificationRepository.get_or_create_delivery(
                delivery_uuid,
                self.channel,
                {"notification_type_id": self.kind},
            ).pk

        first, second = self.parallel([create, create])
        self.assertEqual(first, second)
        self.assertEqual(Notification.objects.filter(uuid=delivery_uuid).count(), 1)

    def test_provider_io_holds_no_row_lock(self):
        entered, release = Event(), Event()
        strategy = Mock()

        def send(*args):
            self.assertFalse(connection.in_atomic_block)
            entered.set()
            if not release.wait(timeout=10):
                raise RuntimeError("test timeout")
            return True

        strategy.send.side_effect = send

        def deliver():
            n = Notification.objects.get(pk=self.n.pk)
            return NotificationService()._send_notification(n, {})

        def read_while_sending():
            with transaction.atomic():
                with connection.cursor() as cursor:
                    cursor.execute("SET LOCAL lock_timeout = '1000ms'")
                n = Notification.objects.select_for_update().get(pk=self.n.pk)
                self.assertEqual(n.status, Notification.Status.SENDING)
                NotificationRepository.mark_as_read(n)

        with (
            patch(
                "notifications.factories.channel_factory.NotificationChannelFactory.create",
                return_value=strategy,
            ),
            patch.object(NotificationService, "_get_template_for_channel", return_value=Mock()),
            ThreadPoolExecutor(max_workers=2) as pool,
        ):
            sending = pool.submit(self.worker, deliver)
            try:
                self.assertTrue(entered.wait(timeout=10))
                pool.submit(self.worker, read_while_sending).result(timeout=5)
            finally:
                release.set()
            sending.result(timeout=15)
        self.n.refresh_from_db()
        self.assertEqual(self.n.status, Notification.Status.READ)
        self.assertTrue(self.n.is_read)
        strategy.send.assert_called_once()

    def test_cancel_and_dispatch_boundary_have_only_one_winner(self):
        self.assertTrue(NotificationRepository.claim_for_send(self.n))
        barrier = Barrier(2)

        def cancel():
            n = Notification.objects.get(pk=self.n.pk)
            barrier.wait(timeout=10)
            return NotificationRepository.cancel(n)

        def begin():
            n = Notification.objects.get(pk=self.n.pk)
            barrier.wait(timeout=10)
            return NotificationRepository.begin_dispatch(n)

        self.assertEqual(sum(self.parallel([cancel, begin])), 1)
        self.n.refresh_from_db()
        if self.n.status == Notification.Status.CANCELLED:
            self.assertIsNone(self.n.dispatch_started_at)
        else:
            self.assertIsNotNone(self.n.dispatch_started_at)
