# ============================================================================
# MANAGEMENT COMMANDS
# ============================================================================

"""
management/commands/send_test_notification.py
Comando para enviar notificaciones de prueba
"""

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "Envía una notificación de prueba"

    def add_arguments(self, parser):
        parser.add_argument("user_id", type=int, help="ID del usuario")
        parser.add_argument("event_code", type=str, help="Código del evento")
        parser.add_argument("--email", type=str, help="Email del destinatario")
        parser.add_argument("--async", action="store_true", help="Enviar async")

    def handle(self, *args, **options):
        from datetime import timezone

        from notifications.services.email_service import EmailNotificationService
        from notifications.tasks import send_email_notification_async

        user_id = options["user_id"]
        event_code = options["event_code"]
        use_async = options.get("async", False)

        User = get_user_model()
        try:
            user = User.objects.get(id=user_id)
        except User.DoesNotExist:
            self.stdout.write(self.style.ERROR(f"Usuario {user_id} no encontrado"))
            return

        email = options.get("email") or user.email

        context = {
            "user_name": user.get_full_name() or user.username,
            "user_email": email,
            "test_data": "Esta es una notificación de prueba",
            "timestamp": timezone.now().isoformat(),
        }

        if use_async:
            task_id = send_email_notification_async.delay(
                event_code=event_code,
                user_id=user_id,
                user_email=email,
                context=context,
            )
            self.stdout.write(
                self.style.SUCCESS(f"Notificación enviada async. Task ID: {task_id}")
            )
        else:
            service = EmailNotificationService()
            notification = service.send_email_notification(
                event_code=event_code,
                user_id=user_id,
                user_email=email,
                context=context,
            )

            if notification:
                self.stdout.write(
                    self.style.SUCCESS(f"Notificación enviada: {notification.uuid}")
                )
            else:
                self.stdout.write(self.style.ERROR("Error enviando notificación"))
