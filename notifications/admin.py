# ============================================================================
# ADMIN CONFIGURATION
# ============================================================================

"""
admin.py - Configuración del Admin de Django para la app de notificaciones.
"""

from django.contrib import admin
from django.utils.html import format_html

from notifications.models import (
    DeviceToken,
    EmailTemplate,
    InAppTemplate,
    Notification,
    NotificationCategory,
    NotificationChannel,
    NotificationLog,
    NotificationType,
    NotificationTypeChannels,
    PushTemplate,
    SlackTemplate,
    SMSTemplate,
    TelegramTemplate,
    UserExternalAccount,
    UserNotificationPreference,
    WebhookTemplate,
    WhatsAppTemplate,
)


# ============================================================================
# INLINES
# ============================================================================

class NotificationTypeChannelsInline(admin.TabularInline):
    model = NotificationTypeChannels
    extra = 1


class NotificationLogInline(admin.TabularInline):
    model = NotificationLog
    extra = 0
    readonly_fields = ["timestamp", "action", "details", "error_message"]
    can_delete = False

    def has_add_permission(self, request, obj=None):
        return False


# ============================================================================
# NOTIFICATION ADMIN
# ============================================================================

@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    list_display = [
        "uuid",
        "notification_type_display",
        "user_display",
        "channel_display",
        "status_badge",
        "is_read",
        "sent_at",
        "retry_count",
    ]
    list_filter = [
        "status",
        "channel_id",
        "is_read",
        "notification_type_id__category_id",
        "created_at",
    ]
    search_fields = [
        "uuid",
        "user_id__email",
        "user_id__username",
        "notification_type_id__event_code",
        "external_id",
    ]
    readonly_fields = ["uuid", "created_at", "updated_at", "sent_at", "delivered_at", "read_at"]
    date_hierarchy = "created_at"
    inlines = [NotificationLogInline]

    fieldsets = (
        (
            "Información General",
            {"fields": ("uuid", "notification_type_id", "user_id", "channel_id")},
        ),
        ("Estado", {"fields": ("status", "is_read", "sent_at", "delivered_at", "read_at", "retry_count")}),
        (
            "Contenido",
            {
                "fields": ("context_data", "rendered_content", "recipient_identifier"),
                "classes": ("collapse",),
            },
        ),
        (
            "Errores y Tracking",
            {
                "fields": ("error_message", "error_code", "external_id"),
                "classes": ("collapse",),
            },
        ),
        (
            "Programación",
            {"fields": ("scheduled_for",), "classes": ("collapse",)},
        ),
        (
            "Auditoría",
            {"fields": ("created_at", "updated_at"), "classes": ("collapse",)},
        ),
    )

    def notification_type_display(self, obj):
        return obj.notification_type_id.event_code
    notification_type_display.short_description = "Tipo"

    def user_display(self, obj):
        if obj.user_id:
            return f"{obj.user_id.username} ({obj.user_id.email})"
        return "-"
    user_display.short_description = "Usuario"

    def channel_display(self, obj):
        return obj.channel_id.name
    channel_display.short_description = "Canal"

    def status_badge(self, obj):
        colors = {
            "pending": "#ffc107",
            "queued": "#17a2b8",
            "sending": "#007bff",
            "sent": "#28a745",
            "delivered": "#20c997",
            "read": "#6f42c1",
            "failed": "#dc3545",
            "cancelled": "#6c757d",
        }
        color = colors.get(obj.status, "#6c757d")
        return format_html(
            '<span style="background-color: {}; color: white; '
            'padding: 3px 10px; border-radius: 3px;">{}</span>',
            color,
            obj.get_status_display(),
        )
    status_badge.short_description = "Estado"

    actions = ["mark_as_sent", "retry_failed", "mark_as_read", "cancel_pending"]

    @admin.action(description="Marcar como enviadas")
    def mark_as_sent(self, request, queryset):
        from notifications.repositories import NotificationRepository
        count = 0
        for notification in queryset:
            NotificationRepository.mark_as_sent(notification)
            count += 1
        self.message_user(request, f"{count} notificaciones marcadas como enviadas.")

    @admin.action(description="Reintentar envío")
    def retry_failed(self, request, queryset):
        from notifications.tasks import send_notification_async
        count = 0
        for notification in queryset.filter(status="failed"):
            send_notification_async.delay({
                "event_code": notification.notification_type_id.event_code,
                "user_id": notification.user_id.id if notification.user_id else None,
                "context": notification.context_data or {},
            })
            count += 1
        self.message_user(request, f"{count} notificaciones enviadas a reintento.")

    @admin.action(description="Marcar como leídas")
    def mark_as_read(self, request, queryset):
        from notifications.repositories import NotificationRepository
        count = 0
        for notification in queryset:
            NotificationRepository.mark_as_read(notification)
            count += 1
        self.message_user(request, f"{count} notificaciones marcadas como leídas.")

    @admin.action(description="Cancelar pendientes")
    def cancel_pending(self, request, queryset):
        count = queryset.filter(status="pending").update(status="cancelled")
        self.message_user(request, f"{count} notificaciones canceladas.")


# ============================================================================
# TEMPLATE ADMINS
# ============================================================================

class BaseTemplateAdmin(admin.ModelAdmin):
    list_filter = ["is_active", "notification_type_id__category_id"]
    search_fields = ["notification_type_id__event_code"]

    def notification_type_display(self, obj):
        return obj.notification_type_id.event_code
    notification_type_display.short_description = "Tipo de Notificación"


@admin.register(EmailTemplate)
class EmailTemplateAdmin(BaseTemplateAdmin):
    list_display = ["template_name", "notification_type_display", "template_subject", "is_active"]
    search_fields = BaseTemplateAdmin.search_fields + ["template_name", "template_subject"]


@admin.register(InAppTemplate)
class InAppTemplateAdmin(BaseTemplateAdmin):
    list_display = ["title", "notification_type_display", "action_url", "is_active"]
    search_fields = BaseTemplateAdmin.search_fields + ["title", "message"]


@admin.register(SMSTemplate)
class SMSTemplateAdmin(BaseTemplateAdmin):
    list_display = ["notification_type_display", "message_preview", "is_active"]

    def message_preview(self, obj):
        return obj.message[:50] + "..." if len(obj.message) > 50 else obj.message
    message_preview.short_description = "Mensaje"


@admin.register(PushTemplate)
class PushTemplateAdmin(BaseTemplateAdmin):
    list_display = ["title", "notification_type_display", "body", "is_active"]
    search_fields = BaseTemplateAdmin.search_fields + ["title", "body"]


@admin.register(WhatsAppTemplate)
class WhatsAppTemplateAdmin(BaseTemplateAdmin):
    list_display = ["notification_type_display", "template_sid", "message_preview", "is_active"]

    def message_preview(self, obj):
        return obj.message[:50] + "..." if len(obj.message) > 50 else obj.message
    message_preview.short_description = "Mensaje"


@admin.register(SlackTemplate)
class SlackTemplateAdmin(BaseTemplateAdmin):
    list_display = ["notification_type_display", "channel_override", "message_preview", "is_active"]

    def message_preview(self, obj):
        return obj.message[:50] + "..." if len(obj.message) > 50 else obj.message
    message_preview.short_description = "Mensaje"


@admin.register(TelegramTemplate)
class TelegramTemplateAdmin(BaseTemplateAdmin):
    list_display = ["notification_type_display", "parse_mode", "message_preview", "is_active"]

    def message_preview(self, obj):
        return obj.message[:50] + "..." if len(obj.message) > 50 else obj.message
    message_preview.short_description = "Mensaje"


@admin.register(WebhookTemplate)
class WebhookTemplateAdmin(BaseTemplateAdmin):
    list_display = ["notification_type_display", "url", "method", "is_active"]


# ============================================================================
# CONFIGURATION ADMINS
# ============================================================================

@admin.register(NotificationType)
class NotificationTypeAdmin(admin.ModelAdmin):
    list_display = ["event_code", "name", "category_id", "get_channels", "is_active"]
    list_filter = ["category_id", "is_active"]
    search_fields = ["event_code", "name"]
    inlines = [NotificationTypeChannelsInline]

    def get_channels(self, obj):
        channels = NotificationTypeChannels.objects.filter(
            notification_type_id=obj
        ).select_related("channel_id")
        return ", ".join([ntc.channel_id.name for ntc in channels])
    get_channels.short_description = "Canales"


@admin.register(NotificationChannel)
class NotificationChannelAdmin(admin.ModelAdmin):
    list_display = ["name", "display_name", "description", "priority", "is_active"]
    list_filter = ["is_active"]
    search_fields = ["name", "display_name"]
    ordering = ["priority", "name"]


@admin.register(NotificationCategory)
class NotificationCategoryAdmin(admin.ModelAdmin):
    list_display = ["name", "description", "icon", "color"]
    search_fields = ["name"]


# ============================================================================
# USER DATA ADMINS
# ============================================================================

@admin.register(DeviceToken)
class DeviceTokenAdmin(admin.ModelAdmin):
    list_display = ["user", "platform", "device_name", "is_active", "last_used_at", "created_at"]
    list_filter = ["platform", "is_active"]
    search_fields = ["user__username", "user__email", "device_name", "device_id"]
    readonly_fields = ["created_at", "updated_at"]

    actions = ["deactivate_tokens"]

    @admin.action(description="Desactivar tokens seleccionados")
    def deactivate_tokens(self, request, queryset):
        count = queryset.update(is_active=False)
        self.message_user(request, f"{count} tokens desactivados.")


@admin.register(UserNotificationPreference)
class UserNotificationPreferenceAdmin(admin.ModelAdmin):
    list_display = ["user", "channel", "notification_type", "is_enabled"]
    list_filter = ["channel", "is_enabled"]
    search_fields = ["user__username", "user__email"]


@admin.register(UserExternalAccount)
class UserExternalAccountAdmin(admin.ModelAdmin):
    list_display = ["user", "account_type", "external_id", "username", "is_verified"]
    list_filter = ["account_type", "is_verified"]
    search_fields = ["user__username", "user__email", "external_id", "username"]


@admin.register(NotificationLog)
class NotificationLogAdmin(admin.ModelAdmin):
    list_display = ["notification", "action", "timestamp", "error_preview"]
    list_filter = ["action", "timestamp"]
    search_fields = ["notification__uuid"]
    readonly_fields = ["notification", "timestamp", "action", "details", "error_message"]
    date_hierarchy = "timestamp"

    def error_preview(self, obj):
        if obj.error_message:
            return obj.error_message[:50] + "..." if len(obj.error_message) > 50 else obj.error_message
        return "-"
    error_preview.short_description = "Error"

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False
