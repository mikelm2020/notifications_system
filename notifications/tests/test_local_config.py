from django.test import SimpleTestCase

from notifications.tasks import send_notification_async


class LocalCeleryConfigTests(SimpleTestCase):
    def test_task_uses_local_broker_and_eager_execution(self):
        self.assertTrue(send_notification_async.app.conf.task_always_eager)
        self.assertEqual(send_notification_async.app.conf.broker_url, "memory://")
        self.assertEqual(send_notification_async.app.conf.result_backend, "cache+memory://")
