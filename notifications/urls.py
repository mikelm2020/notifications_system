# ============================================================================
# NOTIFICATIONS URLS
# ============================================================================

"""
urls.py - URLs de la app de notificaciones.

Incluir en el proyecto principal:
    urlpatterns = [
        path("api/notifications/", include("notifications.urls")),
    ]
"""

from django.urls import include, path
from rest_framework.routers import DefaultRouter

from notifications.views import (
    NotificationViewSet,
    DeviceTokenViewSet,
    UserPreferenceViewSet,
)

app_name = "notifications"

router = DefaultRouter()
router.register(r"notifications", NotificationViewSet, basename="notification")
router.register(r"devices", DeviceTokenViewSet, basename="device")
router.register(r"preferences", UserPreferenceViewSet, basename="preference")

urlpatterns = [
    path("", include(router.urls)),
]
