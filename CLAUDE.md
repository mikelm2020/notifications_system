# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Django-based multi-channel notification system. Supports 9 delivery channels (Email, In-App, SMS, Push FCM, Push Web, WhatsApp, Slack, Telegram, Webhook) with async processing via Celery. Uses Python 3.12, Django 5.0, DRF, Celery 5.5, and Redis.

**This is a self-contained Django app** that can be copied to any Django project.

## Common Commands

```bash
# Development
poetry install                    # Install dependencies
python manage.py runserver        # Run dev server
python manage.py migrate          # Apply migrations
python manage.py makemigrations   # Create migrations

# Celery
celery -A notifications_system worker -l info     # Start worker
celery -A notifications_system beat -l info       # Start scheduler

# Testing
python manage.py test notifications                          # Run all tests
python manage.py test notifications.tests.test_services      # Specific module
python manage.py test notifications.tests.test_services.NotificationServiceTest.test_send_email_notification

# System checks
python manage.py check            # Validates notifications config
```

## Architecture

### Design Patterns

- **Strategy Pattern** (`notifications/strategies/`): Channel-specific delivery logic. Each channel implements `NotificationChannelStrategy` with `prepare_content()` and `send()` methods.

- **Factory Pattern** (`notifications/factories/channel_factory.py`): Creates strategy instances. New channels registered via `register_strategy()`.

- **Repository Pattern** (`notifications/repositories/`): `BaseRepositoryBuilder` provides generic CRUD. Specialized repos extend for model-specific queries.

- **Provider Pattern** (`notifications/providers/`): Abstracts external services (Twilio, Firebase, etc.). Providers implement `BaseProvider` with `send()` and `get_client()`.

- **Template Method** (`NotificationService.create_and_send_notification()`): Orchestrates flow: validate → get channels → filter preferences → create → send.

### Key Modules

| Module | Purpose |
|--------|---------|
| `conf.py` | Centralized config via `NOTIFICATIONS_CONFIG` |
| `exceptions.py` | Custom exception hierarchy |
| `signals.py` | Django signals for hooks (`notification_pre_send`, etc.) |
| `models.py` | All data models including templates for each channel |
| `tasks.py` | Celery tasks for async processing |
| `views.py` | DRF ViewSets for API |
| `serializers.py` | DRF serializers |

### Notification Flow

1. `NotificationData` DTO received with `event_code`, `user_id`, and `context`
2. `NotificationService` validates `NotificationType` exists and is active
3. Gets associated channels from `NotificationTypeChannels`
4. Filters channels by `NOTIFICATIONS_CONFIG` enabled channels
5. Filters by `UserNotificationPreference` (user opt-outs)
6. Creates `Notification` records for each channel (status: PENDING)
7. For each notification:
   - Factory creates appropriate strategy
   - Strategy fetches template model (EmailTemplate, SMSTemplate, etc.)
   - Strategy renders template with context
   - Provider sends to external service
   - Repository updates status (SENT/FAILED)
8. Signals emitted at each step for extensibility

### Channel → Provider → Template Mapping

| Channel | Provider | Template Model |
|---------|----------|----------------|
| email | SMTPProvider | EmailTemplate |
| in_app | None (DB only) | InAppTemplate |
| sms | TwilioProvider | SMSTemplate |
| push_fcm | FCMProvider | PushTemplate |
| push_web | WebPushProvider | PushTemplate |
| whatsapp | TwilioProvider | WhatsAppTemplate |
| slack | SlackProvider | SlackTemplate |
| telegram | TelegramProvider | TelegramTemplate |
| webhook | httpx (direct) | WebhookTemplate |

### Async Processing (Celery)

Tasks in `notifications/tasks.py`:
- `send_notification_async`: Primary entry point (configurable retries)
- `send_email_async`, `send_sms_async`, etc.: Channel-specific shortcuts
- `retry_failed_notifications`: Periodic (every 15 min)
- `process_scheduled_notifications`: Periodic (every min)
- `cleanup_old_notifications`: Periodic (daily)
- `deactivate_expired_device_tokens`: Periodic (weekly)

### Configuration

All config lives in `NOTIFICATIONS_CONFIG` dict in settings:

```python
NOTIFICATIONS_CONFIG = {
    "CHANNELS": {
        "email": {"enabled": True, "provider": "smtp"},
        "sms": {"enabled": True, "provider": "twilio"},
        # ...
    },
    "PROVIDERS": {
        "twilio": {"account_sid": "...", "auth_token": "..."},
        # ...
    },
    "DEFAULTS": {
        "max_retries": 3,
        "retry_delay": 300,
    },
}
```

Access via `notifications_config` singleton:
```python
from notifications.conf import notifications_config
notifications_config.is_channel_enabled("sms")
notifications_config.get_provider_config("twilio")
```

## Adding a New Channel

1. Create provider in `notifications/providers/` implementing `BaseProvider`
2. Create strategy in `notifications/strategies/` implementing `NotificationChannelStrategy`
3. Create template model in `models.py` extending `BaseTemplate`
4. Add to `CHANNEL_TEMPLATE_MAP` in `notification_service.py`
5. Register in `NotificationChannelFactory._initialize()`
6. Add channel to `NotificationChannel.ChannelType` choices
7. Add admin in `admin.py`

## Key Models

- `NotificationCategory`: Groups notification types
- `NotificationType`: Event codes (ORDER_CREATED, etc.)
- `NotificationChannel`: Available channels with ChannelType choices
- `NotificationTypeChannels`: M2M linking types to channels
- `Notification`: Individual notification records with status tracking
- `*Template`: Template models for each channel
- `UserNotificationPreference`: User opt-in/out per channel
- `DeviceToken`: Push notification device tokens
- `UserExternalAccount`: External IDs (Slack, Telegram, etc.)
- `NotificationLog`: Detailed send attempt logs

## API Endpoints

Base path: `/api/notifications/`

- `GET /notifications/` - List user's notifications
- `GET /notifications/{uuid}/` - Notification detail
- `GET /notifications/unread/` - Unread only
- `POST /notifications/{uuid}/mark_read/` - Mark as read
- `POST /notifications/mark_all_read/` - Mark all read
- `GET /notifications/stats/` - User statistics
- `GET/POST /devices/` - Device tokens
- `GET/POST/PUT /preferences/` - User preferences
