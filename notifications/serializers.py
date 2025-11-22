# ============================================================================
# NOTIFICATIONS SERIALIZERS
# ============================================================================

"""
serializers.py - Serializers para la API REST de notificaciones.
"""

from rest_framework import serializers

from notifications.models import (
    DeviceToken,
    Notification,
    NotificationCategory,
    NotificationChannel,
    NotificationType,
    UserExternalAccount,
    UserNotificationPreference,
)


class NotificationChannelSerializer(serializers.ModelSerializer):
    """Serializer para canales de notificación."""

    class Meta:
        model = NotificationChannel
        fields = ["name", "display_name", "description", "icon", "is_active"]


class NotificationCategorySerializer(serializers.ModelSerializer):
    """Serializer para categorías de notificación."""

    class Meta:
        model = NotificationCategory
        fields = ["id", "name", "description", "icon", "color"]


class NotificationTypeSerializer(serializers.ModelSerializer):
    """Serializer para tipos de notificación."""

    category = NotificationCategorySerializer(source="category_id", read_only=True)

    class Meta:
        model = NotificationType
        fields = ["id", "event_code", "name", "description", "category", "is_active"]


class NotificationListSerializer(serializers.ModelSerializer):
    """Serializer para listar notificaciones."""

    type = serializers.CharField(source="notification_type_id.event_code")
    type_name = serializers.CharField(source="notification_type_id.name")
    channel = serializers.CharField(source="channel_id.name")
    content = serializers.JSONField(source="rendered_content")

    class Meta:
        model = Notification
        fields = [
            "uuid",
            "type",
            "type_name",
            "channel",
            "status",
            "is_read",
            "content",
            "created_at",
            "sent_at",
            "read_at",
        ]


class NotificationDetailSerializer(serializers.ModelSerializer):
    """Serializer para detalle de notificación."""

    type = NotificationTypeSerializer(source="notification_type_id")
    channel = NotificationChannelSerializer(source="channel_id")
    content = serializers.JSONField(source="rendered_content")

    class Meta:
        model = Notification
        fields = [
            "uuid",
            "type",
            "channel",
            "status",
            "is_read",
            "content",
            "context_data",
            "created_at",
            "sent_at",
            "delivered_at",
            "read_at",
            "scheduled_for",
            "retry_count",
            "error_message",
        ]


class MarkReadSerializer(serializers.Serializer):
    """Serializer para marcar notificaciones como leídas."""

    uuids = serializers.ListField(
        child=serializers.UUIDField(),
        required=False,
        help_text="Lista de UUIDs a marcar como leídas. Si está vacío, marca todas.",
    )


class DeviceTokenSerializer(serializers.ModelSerializer):
    """Serializer para tokens de dispositivo."""

    class Meta:
        model = DeviceToken
        fields = [
            "id",
            "token",
            "platform",
            "device_id",
            "device_name",
            "is_active",
            "created_at",
            "last_used_at",
        ]
        read_only_fields = ["id", "is_active", "created_at", "last_used_at"]


class DeviceTokenCreateSerializer(serializers.ModelSerializer):
    """Serializer para crear tokens de dispositivo."""

    class Meta:
        model = DeviceToken
        fields = [
            "token",
            "platform",
            "device_id",
            "device_name",
            "endpoint",
            "p256dh_key",
            "auth_key",
        ]

    def validate(self, data):
        """Valida que Web Push tenga los campos requeridos."""
        if data.get("platform") == "web":
            if not all([data.get("endpoint"), data.get("p256dh_key"), data.get("auth_key")]):
                raise serializers.ValidationError(
                    "Web Push requiere endpoint, p256dh_key y auth_key"
                )
        return data

    def create(self, validated_data):
        """Crea o actualiza el token para el usuario."""
        user = self.context["request"].user
        token = validated_data.get("token")

        # Buscar token existente
        existing = DeviceToken.objects.filter(user=user, token=token).first()

        if existing:
            # Actualizar existente
            for key, value in validated_data.items():
                setattr(existing, key, value)
            existing.is_active = True
            existing.save()
            return existing

        # Crear nuevo
        return DeviceToken.objects.create(user=user, **validated_data)


class UserPreferenceSerializer(serializers.ModelSerializer):
    """Serializer para preferencias de notificación."""

    channel_name = serializers.CharField(source="channel.name", read_only=True)
    notification_type_code = serializers.CharField(
        source="notification_type.event_code",
        read_only=True,
        allow_null=True,
    )

    class Meta:
        model = UserNotificationPreference
        fields = [
            "id",
            "channel",
            "channel_name",
            "notification_type",
            "notification_type_code",
            "is_enabled",
        ]
        read_only_fields = ["id"]


class UserPreferenceUpdateSerializer(serializers.Serializer):
    """Serializer para actualizar preferencias en bulk."""

    preferences = serializers.ListField(
        child=serializers.DictField(),
        help_text="Lista de {channel: str, notification_type: int|null, is_enabled: bool}",
    )

    def validate_preferences(self, value):
        """Valida las preferencias."""
        for pref in value:
            if "channel" not in pref or "is_enabled" not in pref:
                raise serializers.ValidationError(
                    "Cada preferencia debe tener 'channel' e 'is_enabled'"
                )
        return value


class ExternalAccountSerializer(serializers.ModelSerializer):
    """Serializer para cuentas externas."""

    class Meta:
        model = UserExternalAccount
        fields = [
            "id",
            "account_type",
            "external_id",
            "username",
            "phone_number",
            "is_verified",
            "created_at",
        ]
        read_only_fields = ["id", "is_verified", "created_at"]


class SendNotificationSerializer(serializers.Serializer):
    """Serializer para enviar notificaciones via API."""

    event_code = serializers.CharField(
        help_text="Código del tipo de notificación (ej: ORDER_CREATED)"
    )
    user_id = serializers.IntegerField(
        required=False,
        help_text="ID del usuario destinatario",
    )
    context = serializers.DictField(
        default=dict,
        help_text="Variables de contexto para los templates",
    )
    scheduled_for = serializers.DateTimeField(
        required=False,
        help_text="Fecha/hora para envío programado",
    )
    channels = serializers.ListField(
        child=serializers.CharField(),
        required=False,
        help_text="Lista de canales específicos (si está vacío, usa todos los configurados)",
    )


class NotificationStatsSerializer(serializers.Serializer):
    """Serializer para estadísticas de notificaciones."""

    total = serializers.IntegerField()
    unread = serializers.IntegerField()
    by_status = serializers.DictField(child=serializers.IntegerField())
    by_channel = serializers.DictField(child=serializers.IntegerField())
