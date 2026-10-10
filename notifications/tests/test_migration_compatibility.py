from uuid import uuid4

from django.db import DatabaseError, IntegrityError, connection
from django.db.migrations.executor import MigrationExecutor
from django.test import TransactionTestCase


class MigrationCompatibilityTests(TransactionTestCase):
    initial = ("notifications", "0001_initial")
    unique = ("notifications", "0002_notification_notification_uuid_channel_unique")

    def setUp(self):
        executor = MigrationExecutor(connection)
        executor.migrate([self.initial])
        self.apps = executor.loader.project_state([self.initial]).apps
        category = self.apps.get_model("notifications", "NotificationCategory").objects.create(
            name="legacy"
        )
        channel = self.apps.get_model("notifications", "NotificationChannel").objects.create(
            name="email"
        )
        kind = self.apps.get_model("notifications", "NotificationType").objects.create(
            category_id=category, event_code="LEGACY"
        )
        self.model = self.apps.get_model("notifications", "Notification")
        self.n = self.model.objects.create(
            notification_type_id=kind,
            channel_id=channel,
            status="sent",
            context_data={"audit": "preserve"},
            external_id="provider-accepted",
        )

    def tearDown(self):
        executor = MigrationExecutor(connection)
        executor.migrate(executor.loader.graph.leaf_nodes())
        super().tearDown()

    def test_initial_to_unique_to_latest_preserves_existing_record(self):
        executor = MigrationExecutor(connection)
        executor.migrate([self.unique])
        executor = MigrationExecutor(connection)
        executor.migrate(executor.loader.graph.leaf_nodes())
        from notifications.models import Notification

        n = Notification.objects.get(pk=self.n.pk)
        self.assertEqual(n.uuid, self.n.uuid)
        self.assertEqual(n.status, "sent")
        self.assertEqual(n.context_data, {"audit": "preserve"})
        self.assertEqual(n.external_id, "provider-accepted")
        self.assertIsNone(n.failed_permanently_at)
        self.assertIsNone(n.dispatch_started_at)

    def test_unique_migration_rejects_duplicates_without_deleting_records(self):
        duplicate = self.model.objects.create(
            uuid=self.n.uuid,
            notification_type_id_id=self.n.notification_type_id_id,
            channel_id_id=self.n.channel_id_id,
            status="failed",
        )
        try:
            with self.assertRaises(IntegrityError):
                MigrationExecutor(connection).migrate([self.unique])
            self.assertEqual(self.model.objects.count(), 2)
            self.assertEqual(self.model.objects.get(pk=self.n.pk).status, "sent")
        finally:
            # Only isolated test fixtures are changed so subsequent tests can migrate.
            self.model.objects.filter(pk=duplicate.pk).update(uuid=uuid4())

    def test_initial_will_not_silently_adopt_existing_tables(self):
        executor = MigrationExecutor(connection)
        migration = executor.loader.get_migration(*self.initial)
        auth_leaf = next(node for node in executor.loader.graph.leaf_nodes() if node[0] == "auth")
        state = executor.loader.project_state([auth_leaf])
        with self.assertRaises(DatabaseError):
            executor.apply_migration(state, migration)
        self.assertEqual(self.model.objects.count(), 1)

    def test_fake_initial_detection_checks_table_presence_not_schema(self):
        executor = MigrationExecutor(connection)
        migration = executor.loader.get_migration(*self.initial)
        # Read-only detection; no migration is fake-applied or artificially recorded.
        applied, _ = executor.detect_soft_applied(None, migration)
        self.assertTrue(applied)
        field = self.model._meta.get_field("rendered_content")
        with connection.schema_editor() as editor:
            editor.remove_field(self.model, field)
        try:
            detected, _ = executor.detect_soft_applied(None, migration)
            self.assertTrue(detected)
        finally:
            with connection.schema_editor() as editor:
                editor.add_field(self.model, field)
