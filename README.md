# Django Notifications System

Sistema de notificaciones multi-canal para Django. Soporta Email, SMS, Push (FCM/Web), WhatsApp, Slack, Telegram y Webhooks.

## Características

- **9 canales de notificación**: Email, In-App, SMS, Push FCM, Push Web, WhatsApp, Slack, Telegram, Webhook
- **Arquitectura extensible**: Patrón Strategy para canales, Factory para instanciación
- **Proveedores intercambiables**: Twilio, Firebase, Slack SDK, etc.
- **Preferencias de usuario**: Control granular por usuario y tipo de notificación
- **Async con Celery**: Procesamiento en background con reintentos automáticos
- **Templates dinámicos**: Sintaxis Django para personalización
- **API REST completa**: ViewSets DRF incluidos
- **Admin configurado**: Gestión completa desde Django Admin

## Instalación

### 1. Copiar la app

Copia el directorio `notifications/` a tu proyecto Django.

### 2. Agregar a INSTALLED_APPS

```python
INSTALLED_APPS = [
    # ...
    "rest_framework",
    "notifications",
]
```

### 3. Agregar URLs

```python
# urls.py
urlpatterns = [
    # ...
    path("api/notifications/", include("notifications.urls")),
]
```

### 4. Ejecutar migraciones

```bash
python manage.py makemigrations notifications
python manage.py migrate
```

### 5. Configurar canales (opcional)

```python
# settings.py
NOTIFICATIONS_CONFIG = {
    "CHANNELS": {
        "email": {"enabled": True},
        "in_app": {"enabled": True},
        "sms": {"enabled": True, "provider": "twilio"},
        "push_fcm": {"enabled": True, "provider": "fcm"},
        "whatsapp": {"enabled": True, "provider": "twilio"},
        "slack": {"enabled": True, "provider": "slack"},
    },
    "PROVIDERS": {
        "twilio": {
            "account_sid": "ACxxxxx",
            "auth_token": "xxxxx",
            "from_number": "+1234567890",
            "whatsapp_from": "whatsapp:+1234567890",
        },
        "fcm": {
            "credentials_path": "/path/to/service-account.json",
        },
        "slack": {
            "bot_token": "xoxb-xxxxx",
        },
    },
}
```

## Dependencias Opcionales

Instala según los canales que uses:

```bash
# SMS y WhatsApp (Twilio)
pip install twilio

# Push FCM (Firebase)
pip install firebase-admin

# Push Web
pip install pywebpush

# Slack
pip install slack-sdk

# Telegram y Webhook
pip install httpx

# WebSocket In-App (tiempo real)
pip install channels
```

## Uso Básico

### Enviar notificación

```python
from notifications.dtos.notification_data import NotificationData
from notifications.services.notification_service import NotificationService

# Crear datos de notificación
notification_data = NotificationData(
    event_code="ORDER_CREATED",
    user_id=user.id,
    context={
        "order_number": "12345",
        "total": "$99.99",
        "user_email": user.email,  # Para email
        "phone_number": user.phone,  # Para SMS/WhatsApp
    },
)

# Enviar por todos los canales configurados
service = NotificationService()
notifications = service.create_and_send_notification(notification_data)

# O enviar solo por canales específicos
notifications = service.create_and_send_notification(
    notification_data,
    channels=["email", "push_fcm"],
)
```

### Enviar asíncronamente (Celery)

```python
from notifications.tasks import send_notification_async

send_notification_async.delay({
    "event_code": "ORDER_CREATED",
    "user_id": user.id,
    "context": {"order_number": "12345"},
})
```

### Tareas especializadas

```python
from notifications.tasks import (
    send_email_async,
    send_sms_async,
    send_push_async,
    send_whatsapp_async,
)

# Email
send_email_async.delay("ORDER_CREATED", user.id, user.email, {"order": "123"})

# SMS
send_sms_async.delay("ORDER_CREATED", user.id, "+1234567890", {"order": "123"})

# Push
send_push_async.delay("ORDER_CREATED", user.id, {"order": "123"})

# WhatsApp
send_whatsapp_async.delay("ORDER_CREATED", user.id, "+1234567890", {"order": "123"})
```

## Configuración de Tipos de Notificación

Desde Django Admin o programáticamente:

```python
from notifications.models import (
    NotificationCategory,
    NotificationType,
    NotificationChannel,
    NotificationTypeChannels,
    EmailTemplate,
)

# Crear categoría
category = NotificationCategory.objects.create(
    name="Transaccional",
    description="Notificaciones de transacciones",
)

# Crear tipo
notification_type = NotificationType.objects.create(
    category_id=category,
    event_code="ORDER_CREATED",
    name="Orden Creada",
)

# Obtener canal
email_channel = NotificationChannel.objects.get(name="email")

# Asociar canal al tipo
NotificationTypeChannels.objects.create(
    notification_type_id=notification_type,
    channel_id=email_channel,
)

# Crear template
EmailTemplate.objects.create(
    notification_type_id=notification_type,
    template_name="order_created_email",
    template_subject="Tu orden #{{ order_number }} ha sido creada",
    template_text="Hola {{ user_name }}, tu orden por {{ total }} está confirmada.",
    template_html="<h1>¡Gracias por tu compra!</h1><p>Orden: {{ order_number }}</p>",
)
```

## API Endpoints

| Endpoint | Método | Descripción |
|----------|--------|-------------|
| `/notifications/` | GET | Lista notificaciones del usuario |
| `/notifications/{uuid}/` | GET | Detalle de notificación |
| `/notifications/unread/` | GET | Notificaciones no leídas |
| `/notifications/{uuid}/mark_read/` | POST | Marcar como leída |
| `/notifications/mark_all_read/` | POST | Marcar todas como leídas |
| `/notifications/stats/` | GET | Estadísticas |
| `/devices/` | GET/POST | Gestionar tokens de dispositivo |
| `/preferences/` | GET/POST/PUT | Gestionar preferencias |

## Celery Beat (Tareas Periódicas)

```python
# celery.py
app.conf.beat_schedule = {
    "retry-failed-notifications": {
        "task": "notifications.tasks.retry_failed_notifications",
        "schedule": crontab(minute="*/15"),
    },
    "process-scheduled-notifications": {
        "task": "notifications.tasks.process_scheduled_notifications",
        "schedule": crontab(minute="*"),
    },
    "cleanup-old-notifications": {
        "task": "notifications.tasks.cleanup_old_notifications",
        "schedule": crontab(hour=3, minute=0),
    },
    "deactivate-expired-tokens": {
        "task": "notifications.tasks.deactivate_expired_device_tokens",
        "schedule": crontab(day_of_week=0, hour=4),
    },
}
```

## Signals

```python
from notifications.signals import (
    notification_pre_create,
    notification_post_create,
    notification_pre_send,
    notification_post_send,
    notification_read,
    notification_failed_permanently,
)

# Ejemplo: Log cuando se envía
@receiver(notification_post_send)
def log_notification(sender, notification, success, **kwargs):
    if success:
        logger.info(f"Notificación {notification.uuid} enviada")
```

## Agregar Canal Personalizado

```python
# my_app/strategies/custom_strategy.py
from notifications.strategies.base_strategy import NotificationChannelStrategy

class CustomChannelStrategy(NotificationChannelStrategy):
    channel_name = "custom"

    def prepare_content(self, template, context):
        return {"message": template.message}

    def send(self, notification, content):
        # Tu lógica de envío
        return True

# Registrar
from notifications.factories.channel_factory import NotificationChannelFactory
NotificationChannelFactory.register_strategy("custom", CustomChannelStrategy)
```

## Estructura de Archivos

```
notifications/
├── __init__.py
├── admin.py          # Configuración Django Admin
├── apps.py           # AppConfig
├── checks.py         # System checks
├── conf.py           # Configuración centralizada
├── exceptions.py     # Excepciones personalizadas
├── models.py         # Modelos de datos
├── serializers.py    # Serializers DRF
├── signals.py        # Signals Django
├── tasks.py          # Tareas Celery
├── urls.py           # URLs de la API
├── views.py          # ViewSets
├── dtos/             # Data Transfer Objects
├── factories/        # Factory pattern
├── providers/        # Proveedores externos
├── repositories/     # Acceso a datos
├── services/         # Lógica de negocio
├── strategies/       # Strategy pattern por canal
└── tests/            # Tests
```

## Licencia

MIT
