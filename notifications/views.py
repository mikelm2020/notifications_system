# ============================================================================
# NOTIFICATIONS VIEWS & APIs
# ============================================================================

"""
views.py - ViewSets y APIs para la app de notificaciones.
"""

from django.db.models import Count, Q
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from notifications.models import (
    DeviceToken,
    Notification,
    NotificationChannel,
    UserNotificationPreference,
)
from notifications.serializers import (
    DeviceTokenCreateSerializer,
    DeviceTokenSerializer,
    MarkReadSerializer,
    NotificationDetailSerializer,
    NotificationListSerializer,
    NotificationStatsSerializer,
    SendNotificationSerializer,
    UserPreferenceSerializer,
    UserPreferenceUpdateSerializer,
)


class NotificationViewSet(viewsets.ReadOnlyModelViewSet):
    """
    ViewSet para gestionar notificaciones del usuario.

    Endpoints:
        GET /notifications/ - Lista notificaciones del usuario
        GET /notifications/{uuid}/ - Detalle de una notificación
        GET /notifications/unread/ - Notificaciones no leídas
        POST /notifications/{uuid}/mark_read/ - Marca una como leída
        POST /notifications/mark_all_read/ - Marca todas como leídas
        GET /notifications/stats/ - Estadísticas
        POST /notifications/send/ - Envía una notificación (admin)
    """

    permission_classes = [IsAuthenticated]
    lookup_field = "uuid"

    def get_queryset(self):
        """Retorna notificaciones del usuario actual."""
        return (
            Notification.objects.filter(user_id=self.request.user)
            .select_related("notification_type_id", "channel_id")
            .order_by("-created_at")
        )

    def get_serializer_class(self):
        if self.action == "retrieve":
            return NotificationDetailSerializer
        return NotificationListSerializer

    @action(detail=False, methods=["get"])
    def unread(self, request):
        """Obtiene notificaciones no leídas."""
        notifications = self.get_queryset().filter(is_read=False)
        page = self.paginate_queryset(notifications)

        if page is not None:
            serializer = NotificationListSerializer(page, many=True)
            return self.get_paginated_response(serializer.data)

        serializer = NotificationListSerializer(notifications, many=True)
        return Response({
            "count": notifications.count(),
            "results": serializer.data,
        })

    @action(detail=True, methods=["post"])
    def mark_read(self, request, uuid=None):
        """Marca una notificación como leída."""
        notification = get_object_or_404(
            Notification,
            uuid=uuid,
            user_id=request.user
        )

        if not notification.is_read:
            notification.is_read = True
            notification.status = Notification.Status.READ
            notification.read_at = timezone.now()
            notification.save(update_fields=["is_read", "status", "read_at", "updated_at"])

            # Emitir signal
            from notifications.signals import notification_read
            notification_read.send(
                sender=Notification,
                notification=notification,
                user=request.user,
            )

        return Response({
            "message": "Notificación marcada como leída",
            "uuid": str(notification.uuid),
        })

    @action(detail=False, methods=["post"])
    def mark_all_read(self, request):
        """Marca todas las notificaciones como leídas."""
        serializer = MarkReadSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        uuids = serializer.validated_data.get("uuids")

        queryset = Notification.objects.filter(
            user_id=request.user,
            is_read=False,
        )

        if uuids:
            queryset = queryset.filter(uuid__in=uuids)

        now = timezone.now()
        count = queryset.update(
            is_read=True,
            status=Notification.Status.READ,
            read_at=now,
            updated_at=now,
        )

        return Response({
            "message": f"{count} notificaciones marcadas como leídas",
            "count": count,
        })

    @action(detail=False, methods=["get"])
    def stats(self, request):
        """Obtiene estadísticas de notificaciones del usuario."""
        queryset = Notification.objects.filter(user_id=request.user)

        stats = {
            "total": queryset.count(),
            "unread": queryset.filter(is_read=False).count(),
            "by_status": {},
            "by_channel": {},
        }

        # Por estado
        status_counts = queryset.values("status").annotate(count=Count("id"))
        stats["by_status"] = {
            item["status"]: item["count"] for item in status_counts
        }

        # Por canal
        channel_counts = queryset.values("channel_id__name").annotate(count=Count("id"))
        stats["by_channel"] = {
            item["channel_id__name"]: item["count"] for item in channel_counts
        }

        serializer = NotificationStatsSerializer(stats)
        return Response(serializer.data)

    @action(detail=False, methods=["post"])
    def send(self, request):
        """
        Envía una notificación (requiere permisos especiales).

        Solo para uso administrativo o desde otros servicios.
        """
        if not request.user.is_staff:
            return Response(
                {"error": "Se requieren permisos de staff"},
                status=status.HTTP_403_FORBIDDEN,
            )

        serializer = SendNotificationSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        from notifications.dtos.notification_data import NotificationData
        from notifications.services.notification_service import NotificationService

        try:
            notification_data = NotificationData(
                event_code=serializer.validated_data["event_code"],
                user_id=serializer.validated_data.get("user_id"),
                context=serializer.validated_data.get("context", {}),
                scheduled_for=serializer.validated_data.get("scheduled_for"),
            )

            service = NotificationService()
            notifications = service.create_and_send_notification(notification_data)

            return Response({
                "message": f"{len(notifications)} notificaciones creadas",
                "notification_ids": [str(n.uuid) for n in notifications],
            })

        except Exception as e:
            return Response(
                {"error": str(e)},
                status=status.HTTP_400_BAD_REQUEST,
            )


class DeviceTokenViewSet(viewsets.ModelViewSet):
    """
    ViewSet para gestionar tokens de dispositivo (Push notifications).

    Endpoints:
        GET /devices/ - Lista dispositivos del usuario
        POST /devices/ - Registra un nuevo dispositivo
        DELETE /devices/{id}/ - Elimina un dispositivo
    """

    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return DeviceToken.objects.filter(user=self.request.user, is_active=True)

    def get_serializer_class(self):
        if self.action == "create":
            return DeviceTokenCreateSerializer
        return DeviceTokenSerializer

    def perform_create(self, serializer):
        device = serializer.save()

        # Emitir signal
        from notifications.signals import device_registered
        device_registered.send(
            sender=DeviceToken,
            device=device,
            user=self.request.user,
            platform=device.platform,
        )

    def perform_destroy(self, instance):
        # Soft delete
        instance.is_active = False
        instance.save()

        # Emitir signal
        from notifications.signals import device_deactivated
        device_deactivated.send(
            sender=DeviceToken,
            device=instance,
            user=self.request.user,
            reason="manual",
        )

    @action(detail=False, methods=["delete"])
    def logout_all(self, request):
        """Desactiva todos los dispositivos del usuario."""
        count = DeviceToken.objects.filter(
            user=request.user,
            is_active=True,
        ).update(is_active=False)

        return Response({
            "message": f"{count} dispositivos desactivados",
            "count": count,
        })


class UserPreferenceViewSet(viewsets.ModelViewSet):
    """
    ViewSet para gestionar preferencias de notificación.

    Endpoints:
        GET /preferences/ - Lista preferencias del usuario
        POST /preferences/ - Crea una preferencia
        PUT /preferences/{id}/ - Actualiza una preferencia
        POST /preferences/bulk_update/ - Actualiza múltiples preferencias
    """

    permission_classes = [IsAuthenticated]
    serializer_class = UserPreferenceSerializer

    def get_queryset(self):
        return UserNotificationPreference.objects.filter(
            user=self.request.user
        ).select_related("channel", "notification_type")

    def perform_create(self, serializer):
        serializer.save(user=self.request.user)

    @action(detail=False, methods=["post"])
    def bulk_update(self, request):
        """Actualiza múltiples preferencias a la vez."""
        serializer = UserPreferenceUpdateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        updated = 0
        created = 0

        for pref_data in serializer.validated_data["preferences"]:
            channel_name = pref_data["channel"]
            notification_type_id = pref_data.get("notification_type")
            is_enabled = pref_data["is_enabled"]

            try:
                channel = NotificationChannel.objects.get(name=channel_name)
            except NotificationChannel.DoesNotExist:
                continue

            preference, was_created = UserNotificationPreference.objects.update_or_create(
                user=request.user,
                channel=channel,
                notification_type_id=notification_type_id,
                defaults={"is_enabled": is_enabled},
            )

            if was_created:
                created += 1
            else:
                updated += 1

            # Emitir signal
            from notifications.signals import preference_changed
            preference_changed.send(
                sender=UserNotificationPreference,
                preference=preference,
                user=request.user,
                channel=channel_name,
                is_enabled=is_enabled,
            )

        return Response({
            "message": f"{created} creadas, {updated} actualizadas",
            "created": created,
            "updated": updated,
        })

    @action(detail=False, methods=["get"])
    def available_channels(self, request):
        """Lista los canales disponibles para configurar."""
        from notifications.factories.channel_factory import NotificationChannelFactory

        channels = NotificationChannel.objects.filter(is_active=True)
        enabled_channels = NotificationChannelFactory.get_enabled_channels()

        data = []
        for channel in channels:
            is_configured = channel.name in enabled_channels
            data.append({
                "name": channel.name,
                "display_name": channel.display_name or channel.get_name_display(),
                "description": channel.description,
                "icon": channel.icon,
                "is_configured": is_configured,
            })

        return Response(data)
