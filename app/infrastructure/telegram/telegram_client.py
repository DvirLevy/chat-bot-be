import logging
from typing import Callable, Awaitable, Any

from telegram import Bot
from telegram.ext import Application, MessageHandler, filters

logger = logging.getLogger("chatbot.telegram")


class TelegramClient:

    def __init__(self, token: str) -> None:
        self._token = token
        self._app: Application = Application.builder().token(token).build()

    def add_message_handler(
        self,
        callback: Callable[..., Awaitable[Any]],
    ) -> None:
        self._app.add_handler(
            MessageHandler(filters.TEXT & ~filters.COMMAND, callback)
        )
        logger.debug("Message handler registered")

    async def start(self) -> None:
        await self._app.initialize()
        await self._app.start()
        await self._app.updater.start_polling(drop_pending_updates=True)
        logger.info("Telegram bot started (polling)")

    async def stop(self) -> None:
        if self._app.updater.running:
            await self._app.updater.stop()
        await self._app.stop()
        await self._app.shutdown()
        logger.info("Telegram bot stopped")

    async def send_message(self, chat_id: int, text: str) -> None:
        bot: Bot = self._app.bot
        await bot.send_message(chat_id=chat_id, text=text)
        logger.debug("Sent message to chat_id=%d", chat_id)
