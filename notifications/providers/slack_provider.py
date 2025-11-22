# ============================================================================
# SLACK PROVIDER
# ============================================================================

"""
slack_provider.py - Proveedor para notificaciones Slack.

Requiere: pip install slack-sdk
"""

import logging
from typing import Any, Dict, List, Optional

from notifications.providers.base import BaseProvider, ProviderResponse

logger = logging.getLogger(__name__)


class SlackProvider(BaseProvider):
    """
    Proveedor para notificaciones Slack.

    Configuración en NOTIFICATIONS_CONFIG:
        "slack": {
            "bot_token": "xoxb-xxxxx",
            "default_channel": "#general",
            "app_token": "xapp-xxxxx",  # Para Socket Mode (opcional)
        }

    Permisos requeridos del Bot:
        - chat:write
        - chat:write.public (para canales públicos sin estar unido)
        - users:read (para obtener info de usuarios)
    """

    provider_name = "slack"
    required_config_fields = ["bot_token"]

    def get_client(self) -> Any:
        """Obtiene el cliente de Slack."""
        if self._client is None:
            try:
                from slack_sdk import WebClient
                self._client = WebClient(token=self._config["bot_token"])
            except ImportError:
                raise ImportError(
                    "slack-sdk no está instalado. "
                    "Ejecuta: pip install slack-sdk"
                )
        return self._client

    def send(
        self,
        recipient: str,
        content: Dict[str, Any],
        **kwargs
    ) -> ProviderResponse:
        """
        Envía un mensaje a Slack.

        Args:
            recipient: ID de canal (#channel), ID de usuario (Uxxxxx),
                      o ID de conversación (Cxxxxx, Dxxxxx).
            content: Dict con:
                - text: Texto del mensaje (fallback)
                - blocks: Slack Block Kit blocks (opcional)
                - attachments: Attachments legacy (opcional)
            **kwargs:
                - thread_ts: Para responder en un thread
                - reply_broadcast: Broadcast reply al canal
                - unfurl_links: Expandir links
                - unfurl_media: Expandir media

        Returns:
            ProviderResponse con resultado.
        """
        try:
            client = self.get_client()

            # Determinar canal
            channel = recipient
            if channel.startswith("#"):
                # Es un nombre de canal, necesitamos el ID
                channel = self._resolve_channel_name(channel[1:])

            # Preparar mensaje
            message_params = {
                "channel": channel,
                "text": content.get("text", content.get("message", "")),
            }

            # Agregar blocks si existen
            blocks = content.get("blocks")
            if blocks:
                message_params["blocks"] = blocks

            # Agregar attachments si existen
            attachments = content.get("attachments")
            if attachments:
                message_params["attachments"] = attachments

            # Parámetros opcionales
            if kwargs.get("thread_ts"):
                message_params["thread_ts"] = kwargs["thread_ts"]
            if kwargs.get("reply_broadcast"):
                message_params["reply_broadcast"] = True
            if "unfurl_links" in kwargs:
                message_params["unfurl_links"] = kwargs["unfurl_links"]
            if "unfurl_media" in kwargs:
                message_params["unfurl_media"] = kwargs["unfurl_media"]

            # Enviar
            response = client.chat_postMessage(**message_params)

            if response["ok"]:
                logger.info(f"Slack enviado a {channel}: {response['ts']}")
                return ProviderResponse(
                    success=True,
                    message_id=response["ts"],
                    raw_response=dict(response),
                )
            else:
                return ProviderResponse(
                    success=False,
                    error_message=response.get("error", "Unknown error"),
                )

        except Exception as e:
            return self._handle_error(e, f"Error enviando a Slack {recipient}")

    def _resolve_channel_name(self, channel_name: str) -> str:
        """Resuelve un nombre de canal a su ID."""
        try:
            client = self.get_client()
            response = client.conversations_list(types="public_channel,private_channel")

            for channel in response["channels"]:
                if channel["name"] == channel_name:
                    return channel["id"]

            # Si no encontramos, intentamos usar el nombre directamente
            return f"#{channel_name}"

        except Exception:
            return f"#{channel_name}"

    def send_direct_message(
        self,
        user_id: str,
        content: Dict[str, Any],
        **kwargs
    ) -> ProviderResponse:
        """
        Envía un mensaje directo a un usuario.

        Args:
            user_id: ID del usuario de Slack (Uxxxxx).
            content: Contenido del mensaje.
        """
        try:
            client = self.get_client()

            # Abrir conversación con el usuario
            response = client.conversations_open(users=[user_id])
            if not response["ok"]:
                return ProviderResponse(
                    success=False,
                    error_message=f"No se pudo abrir DM: {response.get('error')}",
                )

            channel_id = response["channel"]["id"]
            return self.send(channel_id, content, **kwargs)

        except Exception as e:
            return self._handle_error(e, f"Error enviando DM a {user_id}")

    def send_ephemeral(
        self,
        channel: str,
        user_id: str,
        content: Dict[str, Any],
        **kwargs
    ) -> ProviderResponse:
        """
        Envía un mensaje efímero (solo visible para un usuario).

        Args:
            channel: ID del canal.
            user_id: ID del usuario que verá el mensaje.
            content: Contenido del mensaje.
        """
        try:
            client = self.get_client()

            response = client.chat_postEphemeral(
                channel=channel,
                user=user_id,
                text=content.get("text", ""),
                blocks=content.get("blocks"),
            )

            if response["ok"]:
                return ProviderResponse(
                    success=True,
                    message_id=response.get("message_ts", "ephemeral"),
                )
            else:
                return ProviderResponse(
                    success=False,
                    error_message=response.get("error"),
                )

        except Exception as e:
            return self._handle_error(e, "Error enviando mensaje efímero")

    def update_message(
        self,
        channel: str,
        message_ts: str,
        content: Dict[str, Any],
    ) -> ProviderResponse:
        """Actualiza un mensaje existente."""
        try:
            client = self.get_client()

            response = client.chat_update(
                channel=channel,
                ts=message_ts,
                text=content.get("text", ""),
                blocks=content.get("blocks"),
            )

            if response["ok"]:
                return ProviderResponse(
                    success=True,
                    message_id=response["ts"],
                )
            else:
                return ProviderResponse(
                    success=False,
                    error_message=response.get("error"),
                )

        except Exception as e:
            return self._handle_error(e, "Error actualizando mensaje")
