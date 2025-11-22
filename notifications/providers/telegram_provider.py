# ============================================================================
# TELEGRAM PROVIDER
# ============================================================================

"""
telegram_provider.py - Proveedor para notificaciones Telegram.

Requiere: pip install python-telegram-bot
"""

import logging
from typing import Any, Dict, List, Optional

from notifications.providers.base import BaseProvider, ProviderResponse

logger = logging.getLogger(__name__)


class TelegramProvider(BaseProvider):
    """
    Proveedor para notificaciones Telegram via Bot API.

    Configuración en NOTIFICATIONS_CONFIG:
        "telegram": {
            "bot_token": "123456:ABC-DEF1234ghIkl-zyx57W2v1u123ew11",
        }

    Para crear un bot:
        1. Habla con @BotFather en Telegram
        2. Usa /newbot y sigue las instrucciones
        3. Guarda el token que te da

    Para obtener chat_id de un usuario:
        1. El usuario debe iniciar conversación con tu bot
        2. Usa getUpdates para ver el chat_id
    """

    provider_name = "telegram"
    required_config_fields = ["bot_token"]

    def get_client(self) -> Any:
        """Obtiene el cliente de Telegram (síncrono)."""
        if self._client is None:
            try:
                import httpx
                self._client = httpx.Client(
                    base_url=f"https://api.telegram.org/bot{self._config['bot_token']}"
                )
            except ImportError:
                raise ImportError(
                    "httpx no está instalado. "
                    "Ejecuta: pip install httpx"
                )
        return self._client

    def send(
        self,
        recipient: str,
        content: Dict[str, Any],
        **kwargs
    ) -> ProviderResponse:
        """
        Envía un mensaje a Telegram.

        Args:
            recipient: chat_id del destinatario (usuario, grupo o canal).
            content: Dict con:
                - text: Texto del mensaje
                - parse_mode: "HTML", "Markdown", o "MarkdownV2"
                - disable_web_page_preview: Boolean
                - buttons: Inline keyboard buttons
            **kwargs:
                - reply_to_message_id: ID del mensaje a responder
                - disable_notification: Enviar sin sonido

        Returns:
            ProviderResponse con resultado.
        """
        try:
            client = self.get_client()

            # Preparar payload
            payload = {
                "chat_id": recipient,
                "text": content.get("text", content.get("message", "")),
            }

            # Parse mode
            parse_mode = content.get("parse_mode", "HTML")
            if parse_mode:
                payload["parse_mode"] = parse_mode

            # Disable preview
            if content.get("disable_web_page_preview") or content.get("disable_preview"):
                payload["disable_web_page_preview"] = True

            # Reply to message
            if kwargs.get("reply_to_message_id"):
                payload["reply_to_message_id"] = kwargs["reply_to_message_id"]

            # Silent message
            if kwargs.get("disable_notification"):
                payload["disable_notification"] = True

            # Inline keyboard
            buttons = content.get("buttons")
            if buttons:
                payload["reply_markup"] = {
                    "inline_keyboard": buttons
                }

            # Enviar
            response = client.post("/sendMessage", json=payload)
            data = response.json()

            if data.get("ok"):
                message_id = data["result"]["message_id"]
                logger.info(f"Telegram enviado a {recipient}: {message_id}")
                return ProviderResponse(
                    success=True,
                    message_id=str(message_id),
                    raw_response=data["result"],
                )
            else:
                return ProviderResponse(
                    success=False,
                    error_message=data.get("description", "Unknown error"),
                    error_code=str(data.get("error_code", "")),
                )

        except Exception as e:
            return self._handle_error(e, f"Error enviando a Telegram {recipient}")

    def send_photo(
        self,
        recipient: str,
        photo_url: str,
        caption: str = "",
        **kwargs
    ) -> ProviderResponse:
        """Envía una foto."""
        try:
            client = self.get_client()

            payload = {
                "chat_id": recipient,
                "photo": photo_url,
                "caption": caption,
                "parse_mode": kwargs.get("parse_mode", "HTML"),
            }

            response = client.post("/sendPhoto", json=payload)
            data = response.json()

            if data.get("ok"):
                return ProviderResponse(
                    success=True,
                    message_id=str(data["result"]["message_id"]),
                )
            else:
                return ProviderResponse(
                    success=False,
                    error_message=data.get("description"),
                )

        except Exception as e:
            return self._handle_error(e, "Error enviando foto")

    def send_document(
        self,
        recipient: str,
        document_url: str,
        caption: str = "",
        **kwargs
    ) -> ProviderResponse:
        """Envía un documento."""
        try:
            client = self.get_client()

            payload = {
                "chat_id": recipient,
                "document": document_url,
                "caption": caption,
            }

            response = client.post("/sendDocument", json=payload)
            data = response.json()

            if data.get("ok"):
                return ProviderResponse(
                    success=True,
                    message_id=str(data["result"]["message_id"]),
                )
            else:
                return ProviderResponse(
                    success=False,
                    error_message=data.get("description"),
                )

        except Exception as e:
            return self._handle_error(e, "Error enviando documento")

    def edit_message(
        self,
        chat_id: str,
        message_id: int,
        text: str,
        **kwargs
    ) -> ProviderResponse:
        """Edita un mensaje existente."""
        try:
            client = self.get_client()

            payload = {
                "chat_id": chat_id,
                "message_id": message_id,
                "text": text,
                "parse_mode": kwargs.get("parse_mode", "HTML"),
            }

            if kwargs.get("buttons"):
                payload["reply_markup"] = {"inline_keyboard": kwargs["buttons"]}

            response = client.post("/editMessageText", json=payload)
            data = response.json()

            if data.get("ok"):
                return ProviderResponse(success=True, message_id=str(message_id))
            else:
                return ProviderResponse(
                    success=False,
                    error_message=data.get("description"),
                )

        except Exception as e:
            return self._handle_error(e, "Error editando mensaje")

    def delete_message(self, chat_id: str, message_id: int) -> ProviderResponse:
        """Elimina un mensaje."""
        try:
            client = self.get_client()

            response = client.post("/deleteMessage", json={
                "chat_id": chat_id,
                "message_id": message_id,
            })
            data = response.json()

            return ProviderResponse(
                success=data.get("ok", False),
                error_message=data.get("description") if not data.get("ok") else None,
            )

        except Exception as e:
            return self._handle_error(e, "Error eliminando mensaje")

    def get_chat_info(self, chat_id: str) -> Optional[Dict]:
        """Obtiene información de un chat."""
        try:
            client = self.get_client()
            response = client.post("/getChat", json={"chat_id": chat_id})
            data = response.json()

            if data.get("ok"):
                return data["result"]
            return None

        except Exception:
            return None
