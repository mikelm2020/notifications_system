# ============================================================================
# NOTIFICATIONS APP MODELS
# ============================================================================

import uuid

from django.contrib.auth import get_user_model
from django.db import models
from django.utils.translation import gettext as _

# ============================================================================
# BASE MODELS
# ============================================================================


class Traceable(models.Model):
    """Modelo base con campos de auditoría."""

    created_at = models.DateTimeField(_("Creado en"), auto_now_add=True)
    updated_at = models.DateTimeField(_("Actualizado en"), auto_now=True)

    class Meta:
        abstract = True


class BaseTemplate(Traceable):
    """Modelo base para todos los templates de notificación."""

    notification_type_id = models.ForeignKey(
        "NotificationType",
        on_delete=models.CASCADE,
        verbose_name=_("Tipo de notificación"),
        help_text=_("Tipo de notificación asociada"),
    )
    is_active = models.BooleanField(
        _("Activo"),
        default=True,
        help_text=_("Si el template está activo para uso"),
    )

    class Meta:
        abstract = True


# ============================================================================
# CORE MODELS
# ============================================================================


class NotificationCategory(Traceable):
    """Categorías de notificación para organización."""

    name = models.CharField(_("Nombre"), max_length=150)
    description = models.CharField(_("Descripción"), max_length=150)
    icon = models.CharField(
        _("Icono"),
        max_length=50,
        blank=True,
        help_text=_("Nombre del icono (ej: 'bell', 'mail')"),
    )
    color = models.CharField(
        _("Color"),
        max_length=7,
        blank=True,
        help_text=_("Color hex (ej: '#FF5733')"),
    )

    class Meta:
        verbose_name = _("Categoría de Notificación")
        verbose_name_plural = _("Categorías de Notificación")

    def __str__(self):
        return self.name


class NotificationChannel(models.Model):
    """Canales disponibles para envío de notificaciones."""

    class ChannelType(models.TextChoices):
        EMAIL = "email", _("Email")
        IN_APP = "in_app", _("In-App")
        SMS = "sms", _("SMS")
        PUSH_FCM = "push_fcm", _("Push (FCM)")
        PUSH_WEB = "push_web", _("Push (Web)")
        WHATSAPP = "whatsapp", _("WhatsApp")
        SLACK = "slack", _("Slack")
        TELEGRAM = "telegram", _("Telegram")
        WEBHOOK = "webhook", _("Webhook")

    name = models.CharField(
        _("Nombre"),
        max_length=150,
        unique=True,
        choices=ChannelType.choices,
        help_text=_("Identificador único del canal"),
    )
    display_name = models.CharField(
        _("Nombre para mostrar"),
        max_length=150,
        blank=True,
    )
    description = models.CharField(_("Descripción"), max_length=150)
    icon = models.CharField(
        _("Icono"),
        max_length=50,
        blank=True,
    )
    is_active = models.BooleanField(
        _("Activo"),
        default=True,
        help_text=_("Si el canal está activo globalmente"),
    )
    priority = models.PositiveIntegerField(
        _("Prioridad"),
        default=0,
        help_text=_("Orden de prioridad (menor = más prioritario)"),
    )

    class Meta:
        verbose_name = _("Canal de Notificación")
        verbose_name_plural = _("Canales de Notificación")
        ordering = ["priority", "name"]

    def __str__(self):
        return self.display_name or self.get_name_display()


class NotificationType(Traceable):
    """Tipos de notificación con código de evento único."""

    category_id = models.ForeignKey(
        NotificationCategory,
        on_delete=models.CASCADE,
        verbose_name=_("Categoría"),
        related_name="notification_types",
    )
    event_code = models.CharField(
        _("Código del evento"),
        max_length=150,
        unique=True,
        help_text=_("Código único del evento (ej. ORDER_CREATED, PASSWORD_RESET)"),
    )
    name = models.CharField(
        _("Nombre"),
        max_length=150,
        blank=True,
        help_text=_("Nombre descriptivo del tipo de notificación"),
    )
    description = models.TextField(
        _("Descripción"),
        blank=True,
    )
    is_active = models.BooleanField(
        _("Activo"),
        default=True,
    )

    class Meta:
        verbose_name = _("Tipo de Notificación")
        verbose_name_plural = _("Tipos de Notificación")

    def __str__(self):
        return self.event_code


class NotificationTypeChannels(models.Model):
    """Relación entre tipos de notificación y canales."""

    notification_type_id = models.ForeignKey(
        NotificationType,
        on_delete=models.CASCADE,
        verbose_name=_("Tipo de notificación"),
        related_name="channel_associations",
    )
    channel_id = models.ForeignKey(
        NotificationChannel,
        on_delete=models.CASCADE,
        verbose_name=_("Canal"),
        related_name="type_associations",
    )
    is_required = models.BooleanField(
        _("Requerido"),
        default=False,
        help_text=_("Si el usuario no puede desactivar este canal"),
    )
    priority = models.PositiveIntegerField(
        _("Prioridad"),
        default=0,
        help_text=_("Orden de envío (menor = primero)"),
    )

    class Meta:
        verbose_name = _("Canal del Tipo de Notificación")
        verbose_name_plural = _("Canales del Tipo de Notificación")
        unique_together = ["notification_type_id", "channel_id"]
        ordering = ["priority"]


# ============================================================================
# TEMPLATE MODELS
# ============================================================================


class EmailTemplate(BaseTemplate):
    """Template para notificaciones por email."""

    template_name = models.CharField(_("Nombre"), max_length=150)
    template_subject = models.CharField(_("Asunto"), max_length=255)
    template_text = models.TextField(
        _("Cuerpo (texto plano)"),
        help_text=_("Versión texto plano del email"),
    )
    template_html = models.TextField(
        _("Cuerpo (HTML)"),
        blank=True,
        help_text=_("Versión HTML del email (opcional)"),
    )

    class Meta:
        verbose_name = _("Template de Email")
        verbose_name_plural = _("Templates de Email")

    def __str__(self):
        return self.template_name


class InAppTemplate(BaseTemplate):
    """Template para notificaciones in-app."""

    title = models.CharField(_("Título"), max_length=150)
    message = models.TextField(_("Mensaje"))
    icon = models.CharField(
        _("Icono"),
        max_length=50,
        blank=True,
    )
    action_url = models.CharField(
        _("URL de acción"),
        max_length=500,
        blank=True,
        help_text=_("URL a la que redirigir al hacer click. Soporta variables {{ }}."),
    )
    action_label = models.CharField(
        _("Etiqueta de acción"),
        max_length=50,
        blank=True,
    )

    class Meta:
        verbose_name = _("Template In-App")
        verbose_name_plural = _("Templates In-App")

    def __str__(self):
        return self.title


class SMSTemplate(BaseTemplate):
    """Template para notificaciones SMS."""

    message = models.CharField(
        _("Mensaje"),
        max_length=160,
        help_text=_("Máximo 160 caracteres para un SMS estándar"),
    )

    class Meta:
        verbose_name = _("Template de SMS")
        verbose_name_plural = _("Templates de SMS")

    def __str__(self):
        return f"SMS: {self.notification_type_id.event_code}"


class PushTemplate(BaseTemplate):
    """Template para notificaciones Push (FCM y Web Push)."""

    title = models.CharField(_("Título"), max_length=100)
    body = models.CharField(_("Cuerpo"), max_length=255)
    icon = models.CharField(
        _("URL del icono"),
        max_length=500,
        blank=True,
    )
    image = models.CharField(
        _("URL de imagen"),
        max_length=500,
        blank=True,
        help_text=_("Imagen grande para notificaciones expandidas"),
    )
    click_action = models.CharField(
        _("Acción al click"),
        max_length=500,
        blank=True,
        help_text=_("URL o deep link al hacer click"),
    )
    data = models.JSONField(
        _("Datos adicionales"),
        default=dict,
        blank=True,
        help_text=_("Datos JSON para enviar a la app"),
    )

    class Meta:
        verbose_name = _("Template de Push")
        verbose_name_plural = _("Templates de Push")

    def __str__(self):
        return self.title


class WhatsAppTemplate(BaseTemplate):
    """Template para notificaciones WhatsApp."""

    template_sid = models.CharField(
        _("Template SID"),
        max_length=100,
        blank=True,
        help_text=_("ID del template pre-aprobado en Twilio/Meta"),
    )
    message = models.TextField(
        _("Mensaje"),
        help_text=_("Mensaje con variables {{1}}, {{2}}, etc."),
    )
    header_type = models.CharField(
        _("Tipo de header"),
        max_length=20,
        choices=[
            ("none", "Sin header"),
            ("text", "Texto"),
            ("image", "Imagen"),
            ("document", "Documento"),
            ("video", "Video"),
        ],
        default="none",
    )
    header_content = models.CharField(
        _("Contenido del header"),
        max_length=500,
        blank=True,
    )
    footer = models.CharField(
        _("Footer"),
        max_length=60,
        blank=True,
    )
    buttons = models.JSONField(
        _("Botones"),
        default=list,
        blank=True,
        help_text=_("Lista de botones [{'type': 'url/call', 'text': '...', 'value': '...'}]"),
    )

    class Meta:
        verbose_name = _("Template de WhatsApp")
        verbose_name_plural = _("Templates de WhatsApp")

    def __str__(self):
        return f"WhatsApp: {self.notification_type_id.event_code}"


class SlackTemplate(BaseTemplate):
    """Template para notificaciones Slack."""

    message = models.TextField(
        _("Mensaje"),
        help_text=_("Mensaje en formato Slack markdown"),
    )
    blocks = models.JSONField(
        _("Blocks"),
        default=list,
        blank=True,
        help_text=_("Slack Block Kit JSON para mensajes ricos"),
    )
    channel_override = models.CharField(
        _("Canal override"),
        max_length=100,
        blank=True,
        help_text=_("Canal específico para este tipo de notificación"),
    )

    class Meta:
        verbose_name = _("Template de Slack")
        verbose_name_plural = _("Templates de Slack")

    def __str__(self):
        return f"Slack: {self.notification_type_id.event_code}"


class TelegramTemplate(BaseTemplate):
    """Template para notificaciones Telegram."""

    message = models.TextField(
        _("Mensaje"),
        help_text=_("Mensaje con formato Markdown o HTML de Telegram"),
    )
    parse_mode = models.CharField(
        _("Modo de parseo"),
        max_length=20,
        choices=[
            ("Markdown", "Markdown"),
            ("MarkdownV2", "Markdown V2"),
            ("HTML", "HTML"),
        ],
        default="HTML",
    )
    disable_preview = models.BooleanField(
        _("Desactivar preview"),
        default=False,
    )
    buttons = models.JSONField(
        _("Botones inline"),
        default=list,
        blank=True,
        help_text=_("Lista de botones [[{'text': '...', 'url': '...'}]]"),
    )

    class Meta:
        verbose_name = _("Template de Telegram")
        verbose_name_plural = _("Templates de Telegram")

    def __str__(self):
        return f"Telegram: {self.notification_type_id.event_code}"


class WebhookTemplate(BaseTemplate):
    """Template para notificaciones Webhook."""

    url = models.URLField(
        _("URL del webhook"),
        help_text=_("URL destino. Soporta variables {{ }}."),
    )
    method = models.CharField(
        _("Método HTTP"),
        max_length=10,
        choices=[
            ("POST", "POST"),
            ("PUT", "PUT"),
            ("PATCH", "PATCH"),
        ],
        default="POST",
    )
    headers = models.JSONField(
        _("Headers"),
        default=dict,
        blank=True,
        help_text=_("Headers HTTP adicionales"),
    )
    payload_template = models.TextField(
        _("Payload template"),
        help_text=_("Template JSON del body. Soporta variables {{ }}."),
    )
    timeout = models.PositiveIntegerField(
        _("Timeout (segundos)"),
        default=30,
    )

    class Meta:
        verbose_name = _("Template de Webhook")
        verbose_name_plural = _("Templates de Webhook")

    def __str__(self):
        return f"Webhook: {self.notification_type_id.event_code}"


# ============================================================================
# NOTIFICATION MODEL
# ============================================================================


class Notification(Traceable):
    """Registro de notificaciones enviadas."""

    class Status(models.TextChoices):
        PENDING = "pending", _("Pendiente")
        QUEUED = "queued", _("En cola")
        SENDING = "sending", _("Enviando")
        SENT = "sent", _("Enviada")
        DELIVERED = "delivered", _("Entregada")
        READ = "read", _("Leída")
        FAILED = "failed", _("Fallida")
        CANCELLED = "cancelled", _("Cancelada")

    uuid = models.UUIDField(
        verbose_name="UUID",
        help_text=_("Identificador único de trazabilidad"),
        default=uuid.uuid4,
        editable=False,
        db_index=True,
    )
    notification_type_id = models.ForeignKey(
        NotificationType,
        on_delete=models.CASCADE,
        verbose_name=_("Tipo de notificación"),
        related_name="notifications",
    )
    user_id = models.ForeignKey(
        get_user_model(),
        on_delete=models.CASCADE,
        verbose_name=_("Usuario"),
        related_name="notifications",
        null=True,
        blank=True,
    )
    channel_id = models.ForeignKey(
        NotificationChannel,
        on_delete=models.CASCADE,
        verbose_name=_("Canal"),
        related_name="notifications",
    )
    status = models.CharField(
        _("Estado"),
        max_length=15,
        choices=Status.choices,
        default=Status.PENDING,
        db_index=True,
    )
    is_read = models.BooleanField(_("Leída"), default=False, db_index=True)
    sent_at = models.DateTimeField(_("Fecha de envío"), null=True, blank=True)
    delivered_at = models.DateTimeField(_("Fecha de entrega"), null=True, blank=True)
    read_at = models.DateTimeField(_("Fecha de lectura"), null=True, blank=True)

    # Datos de contexto y contenido renderizado
    context_data = models.JSONField(
        _("Datos de contexto"),
        default=dict,
        blank=True,
    )
    rendered_content = models.JSONField(
        _("Contenido renderizado"),
        default=dict,
        blank=True,
        help_text=_("Contenido final enviado (para auditoría)"),
    )

    # Datos del destinatario
    recipient_identifier = models.CharField(
        _("Identificador del destinatario"),
        max_length=255,
        blank=True,
        help_text=_("Email, teléfono, token, etc."),
    )

    # Errores y reintentos
    error_message = models.TextField(
        _("Mensaje de error"),
        blank=True,
        null=True,
    )
    error_code = models.CharField(
        _("Código de error"),
        max_length=50,
        blank=True,
        null=True,
    )
    retry_count = models.PositiveIntegerField(
        _("Intentos de reenvío"),
        default=0,
    )

    dispatch_started_at = models.DateTimeField(
        _("Inicio de llamada al proveedor"),
        null=True,
        blank=True,
    )
    failed_permanently_at = models.DateTimeField(
        _("Fallo permanente"),
        null=True,
        blank=True,
        db_index=True,
    )

    # Programación
    scheduled_for = models.DateTimeField(
        _("Programado para"),
        null=True,
        blank=True,
        db_index=True,
    )

    # Tracking externo
    external_id = models.CharField(
        _("ID externo"),
        max_length=255,
        blank=True,
        help_text=_("ID del mensaje en el proveedor externo"),
    )

    class Meta:
        verbose_name = _("Notificación")
        verbose_name_plural = _("Notificaciones")
        constraints = [
            models.UniqueConstraint(
                fields=["uuid", "channel_id"], name="notification_uuid_channel_unique"
            ),
        ]
        indexes = [
            models.Index(fields=["user_id", "is_read"]),
            models.Index(fields=["status", "channel_id"]),
            models.Index(fields=["notification_type_id", "status"]),
            models.Index(fields=["created_at"]),
        ]
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.notification_type_id.event_code} - {self.channel_id.name} - {self.status}"


# ============================================================================
# USER PREFERENCES & DEVICES
# ============================================================================


class UserNotificationPreference(Traceable):
    """Preferencias de notificación por usuario y canal."""

    user = models.ForeignKey(
        get_user_model(),
        on_delete=models.CASCADE,
        verbose_name=_("Usuario"),
        related_name="notification_preferences",
    )
    channel = models.ForeignKey(
        NotificationChannel,
        on_delete=models.CASCADE,
        verbose_name=_("Canal"),
        related_name="user_preferences",
    )
    notification_type = models.ForeignKey(
        NotificationType,
        on_delete=models.CASCADE,
        verbose_name=_("Tipo de notificación"),
        related_name="user_preferences",
        null=True,
        blank=True,
        help_text=_("Si es null, aplica a todos los tipos"),
    )
    is_enabled = models.BooleanField(
        _("Habilitado"),
        default=True,
    )

    class Meta:
        verbose_name = _("Preferencia de Notificación")
        verbose_name_plural = _("Preferencias de Notificación")
        unique_together = ["user", "channel", "notification_type"]

    def __str__(self):
        type_str = self.notification_type.event_code if self.notification_type else "ALL"
        return f"{self.user} - {self.channel.name} - {type_str}"


class DeviceToken(Traceable):
    """Tokens de dispositivos para notificaciones Push."""

    class Platform(models.TextChoices):
        IOS = "ios", _("iOS")
        ANDROID = "android", _("Android")
        WEB = "web", _("Web")

    user = models.ForeignKey(
        get_user_model(),
        on_delete=models.CASCADE,
        verbose_name=_("Usuario"),
        related_name="device_tokens",
    )
    token = models.TextField(
        _("Token"),
        help_text=_("Token FCM, APNs o Web Push"),
    )
    platform = models.CharField(
        _("Plataforma"),
        max_length=20,
        choices=Platform.choices,
    )
    device_id = models.CharField(
        _("ID de dispositivo"),
        max_length=255,
        blank=True,
        help_text=_("Identificador único del dispositivo"),
    )
    device_name = models.CharField(
        _("Nombre del dispositivo"),
        max_length=255,
        blank=True,
    )
    is_active = models.BooleanField(
        _("Activo"),
        default=True,
    )
    last_used_at = models.DateTimeField(
        _("Último uso"),
        null=True,
        blank=True,
    )

    # Datos adicionales para Web Push
    endpoint = models.URLField(
        _("Endpoint (Web Push)"),
        blank=True,
    )
    p256dh_key = models.TextField(
        _("Clave P256DH"),
        blank=True,
    )
    auth_key = models.TextField(
        _("Clave Auth"),
        blank=True,
    )

    class Meta:
        verbose_name = _("Token de Dispositivo")
        verbose_name_plural = _("Tokens de Dispositivos")
        unique_together = ["user", "token"]
        indexes = [
            models.Index(fields=["user", "platform", "is_active"]),
        ]

    def __str__(self):
        return f"{self.user} - {self.platform} - {self.device_name or 'Unknown'}"


class UserExternalAccount(Traceable):
    """Cuentas externas de usuario (Slack, Telegram, etc.)."""

    class AccountType(models.TextChoices):
        SLACK = "slack", _("Slack")
        TELEGRAM = "telegram", _("Telegram")
        WHATSAPP = "whatsapp", _("WhatsApp")

    user = models.ForeignKey(
        get_user_model(),
        on_delete=models.CASCADE,
        verbose_name=_("Usuario"),
        related_name="external_accounts",
    )
    account_type = models.CharField(
        _("Tipo de cuenta"),
        max_length=20,
        choices=AccountType.choices,
    )
    external_id = models.CharField(
        _("ID externo"),
        max_length=255,
        help_text=_("ID del usuario en la plataforma externa"),
    )
    username = models.CharField(
        _("Username"),
        max_length=255,
        blank=True,
    )
    phone_number = models.CharField(
        _("Número de teléfono"),
        max_length=20,
        blank=True,
        help_text=_("Para WhatsApp/SMS"),
    )
    is_verified = models.BooleanField(
        _("Verificado"),
        default=False,
    )
    metadata = models.JSONField(
        _("Metadata"),
        default=dict,
        blank=True,
    )

    class Meta:
        verbose_name = _("Cuenta Externa")
        verbose_name_plural = _("Cuentas Externas")
        unique_together = ["user", "account_type", "external_id"]

    def __str__(self):
        return f"{self.user} - {self.account_type} - {self.external_id}"


# ============================================================================
# NOTIFICATION LOG
# ============================================================================


class NotificationLog(models.Model):
    """Log detallado de intentos de envío."""

    notification = models.ForeignKey(
        Notification,
        on_delete=models.CASCADE,
        verbose_name=_("Notificación"),
        related_name="logs",
    )
    timestamp = models.DateTimeField(_("Timestamp"), auto_now_add=True)
    action = models.CharField(
        _("Acción"),
        max_length=50,
        choices=[
            ("created", "Creada"),
            ("queued", "Encolada"),
            ("sending", "Enviando"),
            ("sent", "Enviada"),
            ("delivered", "Entregada"),
            ("read", "Leída"),
            ("failed", "Fallida"),
            ("retrying", "Reintentando"),
            ("cancelled", "Cancelada"),
        ],
    )
    details = models.JSONField(
        _("Detalles"),
        default=dict,
        blank=True,
    )
    error_message = models.TextField(
        _("Mensaje de error"),
        blank=True,
    )

    class Meta:
        verbose_name = _("Log de Notificación")
        verbose_name_plural = _("Logs de Notificación")
        ordering = ["-timestamp"]
        indexes = [
            models.Index(fields=["notification", "timestamp"]),
        ]

    def __str__(self):
        return f"{self.notification.uuid} - {self.action} - {self.timestamp}"
