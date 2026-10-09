from datetime import timedelta
from unittest.mock import Mock, patch
from uuid import uuid4

from celery.exceptions import Retry
from django.contrib.auth import get_user_model
from django.test import TestCase
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
from notifications.repositories.notification_repository import NotificationRepository
from notifications.services.notification_service import NotificationService
from notifications.tasks import (
    process_scheduled_notifications,
    retry_failed_notifications,
    send_notification_async,
    send_to_channel_async,
)


class ReliabilityTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username="reliable", email="a@example.test"
        )
        category = NotificationCategory.objects.create(name="test")
        self.kind = NotificationType.objects.create(category_id=category, event_code="TEST")
        self.channel = NotificationChannel.objects.create(name="email")
        NotificationTypeChannels.objects.create(
            notification_type_id=self.kind, channel_id=self.channel
        )
        EmailTemplate.objects.create(
            notification_type_id=self.kind,
            template_name="test",
            template_subject="Hello",
            template_text="Hello {{ user_email }}",
        )
        self.data = {
            "event_code": "TEST",
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

    def create(self, **kwargs):
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
        notification.refresh_from_db()

    def test_success_and_redelivery_reuse_record(self):
        service = NotificationService()
        first = service.create_and_send_notification(NotificationData(**self.data))[0]
        second = service.create_and_send_notification(NotificationData(**self.data))[0]
        self.assertEqual(first.pk, second.pk)
        self.assertEqual(second.status, Notification.Status.SENT)
        self.assertTrue(timezone.is_aware(second.sent_at))
        self.strategy.send.assert_called_once()

    def test_provider_exception_persists_failure(self):
        self.strategy.send.side_effect = RuntimeError("provider down")
        n = NotificationService().create_and_send_notification(NotificationData(**self.data))[0]
        n.refresh_from_db()
        self.assertEqual(n.status, Notification.Status.FAILED)
        self.assertIn("provider down", n.error_message)

    def test_task_failure_requests_retry(self):
        self.strategy.send.return_value = False
        with patch.object(send_notification_async, "retry", side_effect=Retry()) as retry:
            with self.assertRaises(Retry):
                send_notification_async.run(self.data)
        self.assertEqual(retry.call_args.kwargs["max_retries"], notifications_config.max_retries)
        self.assertEqual(Notification.objects.get().status, Notification.Status.FAILED)

    def test_retry_reuses_failed_record(self):
        self.strategy.send.return_value = False
        service = NotificationService()
        n = service.create_and_send_notification(NotificationData(**self.data))[0]
        self.age(n)
        self.strategy.send.return_value = True
        retried = service.create_and_send_notification(NotificationData(**self.data))[0]
        self.assertEqual(retried.pk, n.pk)
        self.assertEqual(retried.retry_count, 1)
        self.assertEqual(retried.status, Notification.Status.SENT)
        self.assertEqual(Notification.objects.count(), 1)

    def test_periodic_retry_counts_processed_before_status_change(self):
        n = self.create(status=Notification.Status.FAILED)
        self.age(n)
        result = retry_failed_notifications.run()
        self.assertEqual(result, {"processed": 1, "success": 1, "failed": 0})
        n.refresh_from_db()
        self.assertEqual(n.retry_count, 1)

    def test_exhausted_retry_never_sends(self):
        n = self.create(
            status=Notification.Status.FAILED, retry_count=notifications_config.max_retries
        )
        self.age(n)
        NotificationService()._send_notification(n, n.context_data)
        self.strategy.send.assert_not_called()
        self.assertEqual(retry_failed_notifications.run()["processed"], 0)

    def test_retry_delay_is_respected(self):
        n = self.create(status=Notification.Status.FAILED)
        NotificationService()._send_notification(n, n.context_data)
        self.strategy.send.assert_not_called()

    def test_terminal_and_inflight_states_are_not_sent(self):
        for status in ("sent", "delivered", "read", "cancelled", "sending"):
            n = self.create(status=status)
            NotificationService()._send_notification(n, n.context_data)
            n.refresh_from_db()
            self.assertEqual(n.status, status)
        self.strategy.send.assert_not_called()

    def test_stale_worker_cannot_send_twice(self):
        n = self.create()
        stale = Notification.objects.get(pk=n.pk)
        service = NotificationService()
        service._send_notification(n, n.context_data)
        service._send_notification(stale, stale.context_data)
        self.strategy.send.assert_called_once()
        stale.refresh_from_db()
        self.assertEqual(stale.status, Notification.Status.SENT)

    def test_post_send_receiver_failure_does_not_revert_sent(self):
        from notifications.signals import notification_post_send

        def broken_receiver(**kwargs):
            raise RuntimeError("observer")

        notification_post_send.connect(broken_receiver)
        self.addCleanup(notification_post_send.disconnect, broken_receiver)
        with self.assertLogs("django.dispatch", level="ERROR"):
            n = NotificationService().create_and_send_notification(NotificationData(**self.data))[0]
        n.refresh_from_db()
        self.assertEqual(n.status, Notification.Status.SENT)

    def test_scheduled_only_due_notifications_are_sent(self):
        now = timezone.now()
        due = self.create(scheduled_for=now - timedelta(seconds=1))
        future = self.create(scheduled_for=now + timedelta(hours=1))
        self.assertEqual(process_scheduled_notifications.run(), {"processed": 1})
        self.assertEqual(process_scheduled_notifications.run(), {"processed": 0})
        due.refresh_from_db()
        future.refresh_from_db()
        self.assertEqual(due.status, Notification.Status.SENT)
        self.assertEqual(future.status, Notification.Status.PENDING)
        self.strategy.send.assert_called_once()

    def test_scheduled_service_does_not_send_immediately(self):
        data = NotificationData(**self.data, scheduled_for=timezone.now() + timedelta(hours=1))
        n = NotificationService().create_and_send_notification(data)[0]
        self.assertEqual(n.status, Notification.Status.PENDING)
        self.strategy.send.assert_not_called()

    def test_channel_task_reports_failure(self):
        self.strategy.send.return_value = False
        result = send_to_channel_async.run("TEST", self.user.pk, "email", self.data["context"])
        self.assertFalse(result["success"])

    def test_preferences_use_correct_user_field(self):
        UserNotificationPreference.objects.create(
            user=self.user, channel=self.channel, is_enabled=False
        )
        result = NotificationService().create_and_send_notification(NotificationData(**self.data))
        self.assertEqual(result, [])
        self.strategy.send.assert_not_called()

    def test_read_does_not_change_failed_delivery_status(self):
        n = self.create(status=Notification.Status.FAILED)
        NotificationRepository.mark_as_read(n)
        n.refresh_from_db()
        self.assertTrue(n.is_read)
        self.assertEqual(n.status, Notification.Status.FAILED)
        self.assertIsNotNone(n.read_at)

    def test_task_exhaustion_emits_failure_and_raises(self):
        self.strategy.send.return_value = False
        send_notification_async.push_request(retries=notifications_config.max_retries)
        self.addCleanup(send_notification_async.pop_request)
        with patch("notifications.signals.notification_failed_permanently.send_robust") as signal:
            with self.assertRaises(Exception):
                send_notification_async.run(self.data)
        signal.assert_called_once()
        self.assertEqual(Notification.objects.get().status, Notification.Status.FAILED)

    def test_task_retry_without_uuid_preserves_generated_identity(self):
        data = {key: value for key, value in self.data.items() if key != "uuid"}
        self.strategy.send.return_value = False
        send_notification_async.push_request(id="stable-task-id", retries=0)
        self.addCleanup(send_notification_async.pop_request)
        with patch.object(send_notification_async, "retry", side_effect=Retry()) as retry:
            with self.assertRaises(Retry):
                send_notification_async.run(data)
        self.assertEqual(retry.call_args.kwargs["args"], ())
        retry_data = retry.call_args.kwargs["kwargs"]["notification_data_dict"]
        n = Notification.objects.get()
        self.assertEqual(str(n.uuid), retry_data["uuid"])
        self.age(n)
        self.strategy.send.return_value = True
        self.assertTrue(send_notification_async.run(retry_data)["success"])
        self.assertEqual(Notification.objects.count(), 1)
        self.assertNotIn("uuid", data)

    def test_persistence_failure_after_send_leaves_unknown_outcome(self):
        n = self.create()
        with patch.object(
            NotificationRepository, "mark_as_sent", side_effect=RuntimeError("database down")
        ):
            with self.assertRaises(RuntimeError):
                NotificationService()._send_notification(n, n.context_data)
        n.refresh_from_db()
        self.assertEqual(n.status, Notification.Status.SENDING)
        NotificationService()._send_notification(n, n.context_data)
        self.strategy.send.assert_called_once()

    def test_partial_multichannel_retry_skips_successful_channel(self):
        second = NotificationChannel.objects.create(name="in_app")
        from notifications.models import InAppTemplate

        InAppTemplate.objects.create(notification_type_id=self.kind, title="Hi", message="Hi")
        service = NotificationService()
        self.strategy.send.side_effect = [True, False]
        records = service.create_and_send_notification(
            NotificationData(**self.data), ["email", "in_app"]
        )
        failed = next(n for n in records if n.status == Notification.Status.FAILED)
        self.age(failed)
        self.strategy.send.side_effect = None
        self.strategy.send.return_value = True
        retried = service.create_and_send_notification(
            NotificationData(**self.data), ["email", "in_app"]
        )
        self.assertEqual(Notification.objects.count(), 2)
        self.assertTrue(all(n.status == Notification.Status.SENT for n in retried))
        self.assertEqual(self.strategy.send.call_count, 3)
        self.assertIsNotNone(second.pk)

    def test_channel_task_redelivery_preserves_identity(self):
        send_to_channel_async.push_request(id="channel-task-id")
        self.addCleanup(send_to_channel_async.pop_request)
        for _ in range(2):
            self.assertTrue(
                send_to_channel_async.run("TEST", self.user.pk, "email", self.data["context"])[
                    "success"
                ]
            )
        self.assertEqual(Notification.objects.count(), 1)
        self.strategy.send.assert_called_once()

    def test_real_email_strategy_provider_exception_requests_retry(self):
        from notifications.strategies.email_strategy import EmailChannelStrategy

        provider = Mock()
        provider.send.side_effect = RuntimeError("SMTP unavailable")
        strategy = EmailChannelStrategy(provider=provider)
        with (
            patch(
                "notifications.factories.channel_factory.NotificationChannelFactory.create",
                return_value=strategy,
            ),
            patch.object(send_notification_async, "retry", side_effect=Retry()),
        ):
            with self.assertRaises(Retry):
                send_notification_async.run(self.data)
        n = Notification.objects.get()
        self.assertEqual(n.status, Notification.Status.FAILED)
        self.assertEqual(n.error_message, "SMTP unavailable")

    def test_retry_budget_is_shared_with_periodic_task(self):
        self.strategy.send.return_value = False
        n = self.create()
        service = NotificationService()
        service._send_notification(n, n.context_data)
        for _ in range(notifications_config.max_retries):
            self.age(n)
            self.assertEqual(retry_failed_notifications.run()["failed"], 1)
        self.age(n)
        self.assertEqual(retry_failed_notifications.run()["processed"], 0)
        self.assertFalse(service._send_notification(n, n.context_data))
        self.assertEqual(self.strategy.send.call_count, notifications_config.max_retries + 1)

    def test_email_shortcut_redelivery_uses_original_task_identity(self):
        from notifications.tasks import send_email_async

        send_email_async.push_request(id="email-shortcut-task")
        self.addCleanup(send_email_async.pop_request)
        for _ in range(2):
            send_email_async.run("TEST", self.user.pk, self.user.email, {})
        self.assertEqual(Notification.objects.count(), 1)
        self.strategy.send.assert_called_once()

    def test_batch_redelivery_and_failure_reporting(self):
        from notifications.tasks import send_batch_notifications

        data = {key: value for key, value in self.data.items() if key != "uuid"}
        send_batch_notifications.push_request(id="batch-task")
        self.addCleanup(send_batch_notifications.pop_request)
        self.strategy.send.return_value = False
        self.assertEqual(send_batch_notifications.run([data])["failed"], 1)
        n = Notification.objects.get()
        self.age(n)
        self.strategy.send.return_value = True
        self.assertEqual(send_batch_notifications.run([data])["success"], 1)
        self.assertEqual(send_batch_notifications.run([data])["success"], 1)
        self.assertEqual(Notification.objects.count(), 1)
        self.assertEqual(self.strategy.send.call_count, 2)

    def test_exhausted_record_does_not_enqueue_more_retries(self):
        n = self.create(
            uuid=self.data["uuid"],
            status=Notification.Status.FAILED,
            retry_count=notifications_config.max_retries,
        )
        self.age(n)
        with (
            patch.object(send_notification_async, "retry") as retry,
            patch("notifications.signals.notification_failed_permanently.send_robust") as signal,
        ):
            with self.assertRaises(Exception):
                send_notification_async.run(self.data)
        retry.assert_not_called()
        signal.assert_called_once()
        self.strategy.send.assert_not_called()

    def test_actual_celery_retry_signature_preserves_identity_without_duplicate_args(self):
        self.strategy.send.return_value = False
        send_notification_async.push_request(
            id="actual-retry",
            retries=0,
            args=(self.data,),
            kwargs={},
            is_eager=True,
            called_directly=False,
        )
        self.addCleanup(send_notification_async.pop_request)
        with self.assertRaises(Retry) as caught:
            send_notification_async.run(self.data)
        self.assertEqual(caught.exception.sig.args, ())
        self.assertEqual(
            caught.exception.sig.kwargs["notification_data_dict"]["uuid"],
            str(Notification.objects.get().uuid),
        )

    def test_eager_dispatch_sends_without_external_broker(self):
        result = send_notification_async.apply_async(args=(self.data,))
        self.assertTrue(result.get()["success"])
        self.strategy.send.assert_called_once()

    def test_email_resend_uses_saved_context_and_does_not_resend_success(self):
        from notifications.services.email_service import EmailNotificationService

        n = self.create(status=Notification.Status.FAILED)
        self.age(n)
        service = EmailNotificationService()
        self.assertTrue(service.resend_failed_email(str(n.uuid)))
        self.strategy.prepare_content.assert_called_once_with(
            self.template_for_test(), n.context_data
        )
        self.assertTrue(service.resend_failed_email(str(n.uuid)))
        self.strategy.send.assert_called_once()

    def template_for_test(self):
        return EmailTemplate.objects.get(notification_type_id=self.kind)
