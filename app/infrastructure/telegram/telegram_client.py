import logging
from typing import Callable, Awaitable, Any

from telegram import Bot
from telegram.ext import Application, MessageHandler, filters

logger = logging.getLogger("chatbot.telegram")


class TelegramClient:
    """Thin wrapper around python-telegram-bot's Application.

    Lifecycle:
        client = TelegramClient(token)
        client.add_message_handler(callback)   # register before start()
        await client.start()                   # called from FastAPI lifespan
        ...
        await client.stop()                    # called on shutdown

    Handlers must be added *before* calling start(); once the bot is running
    additional handlers are accepted by python-telegram-bot but this wrapper
    enforces the conventional order for clarity.
    """

    def __init__(self, token: str) -> None:
        self._token = token
        # Build the Application immediately (no I/O at construction time).
        self._app: Application = Application.builder().token(token).build()

    def add_message_handler(
        self,
        callback: Callable[..., Awaitable[Any]],
    ) -> None:
        """Register an async callback for plain-text non-command messages."""
        self._app.add_handler(
            MessageHandler(filters.TEXT & ~filters.COMMAND, callback)
        )
        logger.debug("Message handler registered")

    async def start(self) -> None:
        """Initialise the bot and begin polling for updates."""
        await self._app.initialize()
        await self._app.start()
        await self._app.updater.start_polling(drop_pending_updates=True)
        logger.info("Telegram bot started (polling)")

    async def stop(self) -> None:
        """Stop polling and cleanly shut down the bot."""
        if self._app.updater.running:
            await self._app.updater.stop()
        await self._app.stop()
        await self._app.shutdown()
        logger.info("Telegram bot stopped")

    async def send_message(self, chat_id: int, text: str) -> None:
        """Send *text* to the given Telegram chat ID."""
        bot: Bot = self._app.bot
        await bot.send_message(chat_id=chat_id, text=text)
        logger.debug("Sent message to chat_id=%d", chat_id)
