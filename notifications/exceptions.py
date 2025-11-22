# ============================================================================
# NOTIFICATIONS APP EXCEPTIONS
# ============================================================================

"""
exceptions.py - Excepciones personalizadas para la app de notificaciones.
"""


class NotificationError(Exception):
    """Excepción base para errores de notificación."""

    def __init__(self, message: str, code: str = None, details: dict = None):
        self.message = message
        self.code = code or "NOTIFICATION_ERROR"
        self.details = details or {}
        super().__init__(self.message)


# === Errores de Configuración ===

class ConfigurationError(NotificationError):
    """Error de configuración de la app."""

    def __init__(self, message: str, details: dict = None):
        super().__init__(message, "CONFIGURATION_ERROR", details)


class ChannelNotEnabledError(ConfigurationError):
    """Canal no está habilitado en la configuración."""

    def __init__(self, channel_name: str):
        super().__init__(
            f"El canal '{channel_name}' no está habilitado en NOTIFICATIONS_CONFIG",
            {"channel": channel_name}
        )


class ProviderNotConfiguredError(ConfigurationError):
    """Proveedor no está configurado correctamente."""

    def __init__(self, provider_name: str, missing_fields: list = None):
        details = {"provider": provider_name}
        if missing_fields:
            details["missing_fields"] = missing_fields
        super().__init__(
            f"El proveedor '{provider_name}' no está configurado correctamente",
            details
        )


# === Errores de Canal ===

class ChannelError(NotificationError):
    """Error relacionado con un canal de notificación."""

    def __init__(self, message: str, channel: str, details: dict = None):
        details = details or {}
        details["channel"] = channel
        super().__init__(message, "CHANNEL_ERROR", details)


class ChannelNotFoundError(ChannelError):
    """Canal no encontrado o no soportado."""

    def __init__(self, channel_name: str):
        super().__init__(
            f"Canal no encontrado: {channel_name}",
            channel_name,
            {"available_channels": ["email", "in_app", "sms", "push_fcm", "push_web", "whatsapp", "slack", "telegram", "webhook"]}
        )


class ChannelSendError(ChannelError):
    """Error al enviar por un canal específico."""

    def __init__(self, channel: str, reason: str, original_error: Exception = None):
        details = {"reason": reason}
        if original_error:
            details["original_error"] = str(original_error)
        super().__init__(
            f"Error enviando por canal {channel}: {reason}",
            channel,
            details
        )


# === Errores de Template ===

class TemplateError(NotificationError):
    """Error relacionado con templates."""

    def __init__(self, message: str, details: dict = None):
        super().__init__(message, "TEMPLATE_ERROR", details)


class TemplateNotFoundError(TemplateError):
    """Template no encontrado para el tipo de notificación."""

    def __init__(self, notification_type: str, channel: str):
        super().__init__(
            f"No hay template de {channel} para: {notification_type}",
            {"notification_type": notification_type, "channel": channel}
        )


class TemplateRenderError(TemplateError):
    """Error al renderizar un template."""

    def __init__(self, template_name: str, error: str):
        super().__init__(
            f"Error renderizando template '{template_name}': {error}",
            {"template": template_name, "error": error}
        )


# === Errores de Notificación ===

class NotificationTypeNotFoundError(NotificationError):
    """Tipo de notificación no encontrado."""

    def __init__(self, event_code: str):
        super().__init__(
            f"Tipo de notificación no encontrado: {event_code}",
            "NOTIFICATION_TYPE_NOT_FOUND",
            {"event_code": event_code}
        )


class NotificationNotFoundError(NotificationError):
    """Notificación no encontrada."""

    def __init__(self, identifier: str):
        super().__init__(
            f"Notificación no encontrada: {identifier}",
            "NOTIFICATION_NOT_FOUND",
            {"identifier": identifier}
        )


class NoChannelsConfiguredError(NotificationError):
    """No hay canales configurados para el tipo de notificación."""

    def __init__(self, notification_type: str):
        super().__init__(
            f"No hay canales configurados para: {notification_type}",
            "NO_CHANNELS_CONFIGURED",
            {"notification_type": notification_type}
        )


# === Errores de Proveedor ===

class ProviderError(NotificationError):
    """Error de proveedor externo."""

    def __init__(self, provider: str, message: str, details: dict = None):
        details = details or {}
        details["provider"] = provider
        super().__init__(message, "PROVIDER_ERROR", details)


class ProviderConnectionError(ProviderError):
    """Error de conexión con proveedor."""

    def __init__(self, provider: str, error: str):
        super().__init__(
            provider,
            f"Error de conexión con {provider}: {error}",
            {"error": error}
        )


class ProviderAuthenticationError(ProviderError):
    """Error de autenticación con proveedor."""

    def __init__(self, provider: str):
        super().__init__(
            provider,
            f"Error de autenticación con {provider}. Verifica las credenciales.",
        )


class ProviderRateLimitError(ProviderError):
    """Rate limit alcanzado en proveedor."""

    def __init__(self, provider: str, retry_after: int = None):
        details = {}
        if retry_after:
            details["retry_after_seconds"] = retry_after
        super().__init__(
            provider,
            f"Rate limit alcanzado en {provider}",
            details
        )


class ProviderQuotaExceededError(ProviderError):
    """Cuota excedida en proveedor."""

    def __init__(self, provider: str):
        super().__init__(
            provider,
            f"Cuota excedida en {provider}. Revisa tu plan.",
        )


# === Errores de Validación ===

class ValidationError(NotificationError):
    """Error de validación de datos."""

    def __init__(self, message: str, field: str = None, details: dict = None):
        details = details or {}
        if field:
            details["field"] = field
        super().__init__(message, "VALIDATION_ERROR", details)


class InvalidRecipientError(ValidationError):
    """Destinatario inválido."""

    def __init__(self, recipient: str, channel: str, reason: str = None):
        message = f"Destinatario inválido para {channel}: {recipient}"
        if reason:
            message += f" ({reason})"
        super().__init__(
            message,
            "recipient",
            {"recipient": recipient, "channel": channel, "reason": reason}
        )


class InvalidContextError(ValidationError):
    """Contexto de template inválido."""

    def __init__(self, missing_keys: list):
        super().__init__(
            f"Faltan variables en el contexto: {', '.join(missing_keys)}",
            "context",
            {"missing_keys": missing_keys}
        )


# === Errores de Rate Limiting ===

class RateLimitError(NotificationError):
    """Error de rate limiting interno."""

    def __init__(self, user_id: int = None, channel: str = None, retry_after: int = None):
        details = {}
        if user_id:
            details["user_id"] = user_id
        if channel:
            details["channel"] = channel
        if retry_after:
            details["retry_after_seconds"] = retry_after

        super().__init__(
            "Límite de envío alcanzado. Intenta más tarde.",
            "RATE_LIMIT_EXCEEDED",
            details
        )


# === Errores de Dispositivo ===

class DeviceError(NotificationError):
    """Error relacionado con dispositivos (para Push)."""

    def __init__(self, message: str, details: dict = None):
        super().__init__(message, "DEVICE_ERROR", details)


class DeviceTokenInvalidError(DeviceError):
    """Token de dispositivo inválido."""

    def __init__(self, token: str, platform: str = None):
        details = {"token_prefix": token[:10] + "..." if len(token) > 10 else token}
        if platform:
            details["platform"] = platform
        super().__init__(
            "Token de dispositivo inválido o expirado",
            details
        )


class DeviceNotRegisteredError(DeviceError):
    """Dispositivo no registrado."""

    def __init__(self, user_id: int):
        super().__init__(
            "Usuario no tiene dispositivos registrados para Push",
            {"user_id": user_id}
        )
