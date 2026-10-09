# ============================================================================
# TESTS
# ============================================================================

"""
tests/test_notification_service.py
Tests unitarios para el servicio de notificaciones
"""

from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase

from notifications.models import (
    EmailTemplate,
    Notification,
    NotificationCategory,
    NotificationChannel,
    NotificationType,
    NotificationTypeChannels,
)


class NotificationServiceTest(TestCase):
    def setUp(self):
        """Configuración inicial para tests"""
        User = get_user_model()
        self.user = User.objects.create_user(username="testuser", email="test@example.com")

        # Crear categoría
        self.category = NotificationCategory.objects.create(
            name="Transaccional", description="Notificaciones transaccionales"
        )

        # Crear canal
        self.channel = NotificationChannel.objects.create(
            name="email", description="Canal de Email"
        )

        # Crear tipo de notificación
        self.notification_type = NotificationType.objects.create(
            category_id=self.category, event_code="TEST_EVENT"
        )

        # Asociar canal al tipo
        NotificationTypeChannels.objects.create(
            notification_type_id=self.notification_type, channel_id=self.channel
        )

        # Crear template
        self.template = EmailTemplate.objects.create(
            notification_type_id=self.notification_type,
            template_name="Test Template",
            template_subject="Prueba: {{ test_var }}",
            template_text="Hola {{ user_name }}, esto es una prueba.",
        )

    @patch("notifications.providers.smtp.EmailMultiAlternatives.send")
    def test_send_email_notification(self, mock_send_mail):
        """Test de envío de notificación por email"""
        from notifications.services.email_service import EmailNotificationService

        mock_send_mail.return_value = 1

        service = EmailNotificationService()
        notification = service.send_email_notification(
            event_code="TEST_EVENT",
            user_id=self.user.id,
            user_email=self.user.email,
            context={"user_name": "Test User", "test_var": "Valor de Prueba"},
        )

        self.assertIsNotNone(notification)
        self.assertEqual(notification.status, Notification.Status.SENT)
        self.assertEqual(notification.user_id, self.user)
        mock_send_mail.assert_called_once()

    def test_notification_repository_methods(self):
        """Test de métodos del repositorio"""
        from notifications.repositories.notification_repository import NotificationRepository

        # Crear notificación
        notification = Notification.objects.create(
            notification_type_id=self.notification_type,
            user_id=self.user,
            channel_id=self.channel,
            status=Notification.Status.PENDING,
        )

        # Test get_by_uuid
        found = NotificationRepository.get_by_uuid(str(notification.uuid))
        self.assertEqual(found.id, notification.id)

        # Test mark_as_sent
        self.assertTrue(NotificationRepository.claim_for_send(notification))
        self.assertTrue(NotificationRepository.begin_dispatch(notification))
        NotificationRepository.mark_as_sent(notification)
        notification.refresh_from_db()
        self.assertEqual(notification.status, Notification.Status.SENT)
        self.assertIsNotNone(notification.sent_at)

    def test_email_template_rendering(self):
        """Test de renderizado de templates"""
        from notifications.strategies import EmailChannelStrategy

        strategy = EmailChannelStrategy()
        content = strategy.prepare_content(
            self.template,
            {
                "user_name": "Juan Pérez",
                "test_var": "Variable Test",
                "user_email": "juan@test.com",
            },
        )

        self.assertIn("Juan Pérez", content.body)
        self.assertIn("Variable Test", content.subject)
        self.assertEqual(content.to_email, "juan@test.com")
