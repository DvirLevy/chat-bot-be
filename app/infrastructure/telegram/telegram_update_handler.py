import logging
from typing import TYPE_CHECKING

from telegram import Update
from telegram.ext import ContextTypes

if TYPE_CHECKING:
    from app.bl.chat_service import ChatService

logger = logging.getLogger("chatbot.telegram")


class TelegramUpdateHandler:

    def __init__(self, chat_service: "ChatService") -> None:
        self._chat_service = chat_service

    async def handle_message(
        self,
        update: Update,
        context: ContextTypes.DEFAULT_TYPE,
    ) -> None:
        if update.message is None or not update.message.text:
            logger.debug("Received update without text — skipping")
            return

        chat_id: int = update.effective_chat.id
        text: str = update.message.text

        logger.debug(
            "Telegram update received from chat_id=%d (len=%d)", chat_id, len(text)
        )
        await self._chat_service.handle_telegram_message(chat_id=chat_id, text=text)
