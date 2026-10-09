from datetime import timedelta
from unittest.mock import Mock, patch
from uuid import uuid4

from django.contrib.auth import get_user_model
from django.db import transaction
from django.test import TransactionTestCase
from django.utils import timezone

from notifications.conf import notifications_config
from notifications.dtos.notification_data import NotificationData
from notifications.models import (
    EmailTemplate,
    Notification,
    NotificationCategory,
    NotificationChannel,
    NotificationType,
    NotificationTypeChannels,
    UserNotificationPreference,
)
from notifications.services.notification_service import NotificationService
from notifications.signals import notification_pre_send
from notifications.tasks import retry_failed_notifications, send_notification_async


class PostAuditTests(TransactionTestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username="audit", email="audit@example.test"
        )
        category = NotificationCategory.objects.create(name="audit")
        self.kind = NotificationType.objects.create(category_id=category, event_code="AUDIT")
        self.channel = NotificationChannel.objects.create(name="email")
        NotificationTypeChannels.objects.create(
            notification_type_id=self.kind, channel_id=self.channel
        )
        EmailTemplate.objects.create(
            notification_type_id=self.kind,
            template_name="audit",
            template_subject="Hi",
            template_text="Hi",
        )
        self.data = {
            "event_code": "AUDIT",
            "user_id": self.user.pk,
            "context": {"user_email": self.user.email},
            "uuid": str(uuid4()),
        }
        self.strategy = Mock()
        self.strategy.send.return_value = True
        factory = patch(
            "notifications.factories.channel_factory.NotificationChannelFactory.create",
            return_value=self.strategy,
        )
        factory.start()
        self.addCleanup(factory.stop)

    def notification(self, **kwargs):
        return Notification.objects.create(
            notification_type_id=self.kind,
            channel_id=self.channel,
            user_id=self.user,
            context_data=self.data["context"],
            **kwargs,
        )

    def age(self, notification):
        Notification.objects.filter(pk=notification.pk).update(
            updated_at=timezone.now() - timedelta(seconds=notifications_config.retry_delay + 1)
        )

    def test_outer_rollback_never_calls_provider(self):
        n = self.notification()
        with self.assertRaises(RuntimeError):
            with transaction.atomic():
                NotificationService()._send_notification(n, n.context_data)
                self.strategy.send.assert_not_called()
                raise RuntimeError("rollback")
        n.refresh_from_db()
        self.assertEqual(n.status, Notification.Status.PENDING)
        NotificationService()._send_notification(n, n.context_data)
        self.strategy.send.assert_called_once()

    def test_creation_rolled_back_never_calls_provider(self):
        with self.assertRaises(RuntimeError):
            with transaction.atomic():
                NotificationService().create_and_send_notification(NotificationData(**self.data))
                raise RuntimeError("rollback")
        self.assertFalse(Notification.objects.exists())
        self.strategy.send.assert_not_called()

    def test_nested_rollback_discards_deferred_send(self):
        n = self.notification()
        with transaction.atomic():
            try:
                with transaction.atomic():
                    NotificationService()._send_notification(n, n.context_data)
                    raise RuntimeError("savepoint rollback")
            except RuntimeError:
                pass
        self.strategy.send.assert_not_called()
        n.refresh_from_db()
        self.assertEqual(n.status, Notification.Status.PENDING)

    def test_cancel_in_pre_send_prevents_provider_call(self):
        n = self.notification()

        def cancel(sender, notification, **kwargs):
            Notification.objects.filter(pk=notification.pk).update(
                status=Notification.Status.CANCELLED
            )

        notification_pre_send.connect(cancel)
        try:
            NotificationService()._send_notification(n, n.context_data)
        finally:
            notification_pre_send.disconnect(cancel)
        n.refresh_from_db()
        self.assertEqual(n.status, Notification.Status.CANCELLED)
        self.strategy.send.assert_not_called()

    def test_changed_preferences_do_not_hide_failed_record(self):
        n = self.notification(uuid=self.data["uuid"], status=Notification.Status.FAILED)
        self.age(n)
        UserNotificationPreference.objects.create(
            user=self.user, channel=self.channel, is_enabled=False
        )
        result = send_notification_async.run(self.data)
        self.assertFalse(result["success"])
        self.assertIn(str(n.uuid), result["notification_ids"])
        n.refresh_from_db()
        self.assertEqual(n.status, Notification.Status.CANCELLED)
        self.strategy.send.assert_not_called()
        self.assertEqual(retry_failed_notifications.run()["processed"], 0)

    def test_periodic_retry_rechecks_preferences(self):
        n = self.notification(status=Notification.Status.FAILED)
        self.age(n)
        UserNotificationPreference.objects.create(
            user=self.user, channel=self.channel, is_enabled=False
        )
        retry_failed_notifications.run()
        n.refresh_from_db()
        self.assertEqual(n.status, Notification.Status.CANCELLED)
        self.strategy.send.assert_not_called()

    def test_celery_exhaustion_is_persisted_and_prevents_periodic_retry(self):
        self.strategy.send.return_value = False
        send_notification_async.push_request(retries=notifications_config.max_retries)
        try:
            with patch(
                "notifications.signals.notification_failed_permanently.send_robust"
            ) as signal:
                with self.assertRaises(Exception):
                    send_notification_async.run(self.data)
        finally:
            send_notification_async.pop_request()
        n = Notification.objects.get()
        self.assertIsNotNone(n.failed_permanently_at)
        signal.assert_called_once()
        self.age(n)
        self.strategy.send.reset_mock()
        self.assertEqual(retry_failed_notifications.run()["processed"], 0)
        self.strategy.send.assert_not_called()

    def test_timeout_after_possible_acceptance_is_not_retried(self):
        n = self.notification()
        self.strategy.send.side_effect = TimeoutError("accepted, response lost")
        NotificationService()._send_notification(n, n.context_data)
        n.refresh_from_db()
        self.assertEqual(n.status, Notification.Status.SENDING)
        self.assertEqual(n.error_code, "DELIVERY_UNKNOWN")
        self.age(n)
        NotificationService()._send_notification(n, n.context_data)
        self.assertEqual(retry_failed_notifications.run()["processed"], 0)
        self.strategy.send.assert_called_once()

    def test_email_provider_swallowed_timeout_is_not_retried(self):
        from notifications.providers.smtp import SMTPProvider
        from notifications.strategies.email_strategy import EmailChannelStrategy

        provider = SMTPProvider()
        strategy = EmailChannelStrategy(provider=provider)
        n = self.notification()
        with (
            patch(
                "notifications.factories.channel_factory.NotificationChannelFactory.create",
                return_value=strategy,
            ),
            patch(
                "notifications.providers.smtp.EmailMultiAlternatives.send",
                side_effect=TimeoutError("response lost"),
            ),
        ):
            NotificationService()._send_notification(n, n.context_data)
        n.refresh_from_db()
        self.assertEqual(n.status, Notification.Status.SENDING)
        self.assertEqual(n.error_code, "DELIVERY_UNKNOWN")

    def test_permanent_failure_signal_is_emitted_once(self):
        n = self.notification(
            uuid=self.data["uuid"],
            status=Notification.Status.FAILED,
            retry_count=notifications_config.max_retries,
        )
        with patch("notifications.signals.notification_failed_permanently.send_robust") as signal:
            for _ in range(2):
                with self.assertRaises(Exception):
                    send_notification_async.run(self.data)
        signal.assert_called_once()
        n.refresh_from_db()
        self.assertIsNotNone(n.failed_permanently_at)

    def test_cancellation_loses_after_dispatch_boundary(self):
        from notifications.repositories.notification_repository import NotificationRepository

        n = self.notification()
        self.assertTrue(NotificationRepository.claim_for_send(n))
        self.assertTrue(NotificationRepository.begin_dispatch(n))
        self.assertFalse(NotificationRepository.cancel(n))
        self.assertEqual(n.status, Notification.Status.SENDING)

    def test_cancellation_wins_before_dispatch_boundary(self):
        from notifications.repositories.notification_repository import NotificationRepository

        n = self.notification()
        self.assertTrue(NotificationRepository.claim_for_send(n))
        self.assertTrue(NotificationRepository.cancel(n))
        self.assertFalse(NotificationRepository.begin_dispatch(n))
        self.assertEqual(n.status, Notification.Status.CANCELLED)

    def test_cannot_mark_unclaimed_record_as_sent(self):
        from notifications.repositories.notification_repository import NotificationRepository

        for state in (
            Notification.Status.PENDING,
            Notification.Status.FAILED,
            Notification.Status.CANCELLED,
        ):
            n = self.notification(status=state)
            NotificationRepository.mark_as_sent(n)
            self.assertEqual(n.status, state)
            self.assertIsNone(n.sent_at)

    def test_webhook_timeout_does_not_become_retriable_failure(self):
        import httpx

        from notifications.models import WebhookTemplate
        from notifications.strategies.webhook_strategy import WebhookChannelStrategy

        channel = NotificationChannel.objects.create(name="webhook")
        WebhookTemplate.objects.create(
            notification_type_id=self.kind,
            url="https://example.test/hook",
            method="POST",
            payload_template="{}",
        )
        n = Notification.objects.create(notification_type_id=self.kind, channel_id=channel)
        strategy = WebhookChannelStrategy()
        with (
            patch(
                "notifications.factories.channel_factory.NotificationChannelFactory.create",
                return_value=strategy,
            ),
            patch("notifications.strategies.webhook_strategy.httpx.Client") as client,
        ):
            client.return_value.__enter__.return_value.post.side_effect = httpx.ReadTimeout(
                "response lost"
            )
            NotificationService()._send_notification(n, {})
        n.refresh_from_db()
        self.assertEqual(n.status, Notification.Status.SENDING)
        self.assertEqual(n.error_code, "DELIVERY_UNKNOWN")

    def test_ambiguous_task_result_never_requests_retry(self):
        self.strategy.send.side_effect = TimeoutError("accepted, response lost")
        with patch.object(send_notification_async, "retry") as retry:
            result = send_notification_async.run(self.data)
        self.assertFalse(result["success"])
        retry.assert_not_called()
        self.assertEqual(Notification.objects.get().status, Notification.Status.SENDING)

    def test_permanent_receiver_failure_cannot_enable_a_new_attempt(self):
        from notifications.signals import notification_failed_permanently

        n = self.notification(
            uuid=self.data["uuid"],
            status=Notification.Status.FAILED,
            retry_count=notifications_config.max_retries,
        )

        def broken_receiver(**kwargs):
            raise RuntimeError("observer failed")

        notification_failed_permanently.connect(broken_receiver)
        try:
            with self.assertLogs("django.dispatch", level="ERROR"):
                with self.assertRaises(Exception):
                    send_notification_async.run(self.data)
        finally:
            notification_failed_permanently.disconnect(broken_receiver)
        n.refresh_from_db()
        self.assertIsNotNone(n.failed_permanently_at)
        self.assertEqual(retry_failed_notifications.run()["processed"], 0)

    def test_legacy_timeout_record_is_not_automatically_replayed(self):
        n = self.notification(
            uuid=self.data["uuid"],
            status=Notification.Status.FAILED,
            error_code="TIMEOUT",
            error_message="response lost",
        )
        self.age(n)
        with patch.object(send_notification_async, "retry") as retry:
            result = send_notification_async.run(self.data)
        self.assertFalse(result["success"])
        retry.assert_not_called()
        self.assertEqual(retry_failed_notifications.run()["processed"], 0)
        self.strategy.send.assert_not_called()

    def test_periodic_budget_exhaustion_is_terminal_and_notifies_once(self):
        n = self.notification(
            status=Notification.Status.FAILED, retry_count=notifications_config.max_retries - 1
        )
        self.age(n)
        self.strategy.send.return_value = False
        with patch("notifications.signals.notification_failed_permanently.send_robust") as signal:
            self.assertEqual(
                retry_failed_notifications.run(), {"processed": 1, "success": 0, "failed": 1}
            )
            self.assertEqual(retry_failed_notifications.run()["processed"], 0)
        signal.assert_called_once()
        n.refresh_from_db()
        self.assertEqual(n.retry_count, notifications_config.max_retries)
        self.assertIsNotNone(n.failed_permanently_at)
        self.strategy.send.assert_called_once()
