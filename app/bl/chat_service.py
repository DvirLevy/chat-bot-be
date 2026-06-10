"""
ChatService — the central orchestration layer.

Concurrency strategy
--------------------
asyncio is single-threaded and cooperative: a coroutine cannot be interrupted
except at an ``await`` point.  Any code path that performs a logical
*check-then-set* across two repository calls must therefore hold a lock across
both calls so that no other coroutine can interleave between them.

``_assign_lock``
    Guards the "is there an active participant?" check and the subsequent
    ``set_active_chat_id`` call.  Without this lock two simultaneous Telegram
    messages arriving before either is persisted could both see ``active_id``
    as None and both try to become the active participant.

Sequence numbers
    ``ChatStateRepository.get_next_sequence`` performs an atomic
    increment-and-return inside its own lock, so sequence uniqueness and
    ordering are guaranteed without additional locking here.
"""

import asyncio
import logging
from typing import Optional

from app.dal.repositories.chat_state_repository import ChatStateRepository
from app.dal.repositories.message_repository import MessageRepository
from app.helpers.id_helper import generate_id
from app.helpers.time_helper import utcnow_iso
from app.infrastructure.telegram.telegram_client import TelegramClient
from app.infrastructure.websocket.connection_manager import ConnectionManager
from app.models.message import Message
from app.models.websocket_events import MessageEvent

logger = logging.getLogger("chatbot.service")

REJECTED_MESSAGE = "Bot is already connected to another participant."


class ChatService:
    """Orchestrates message routing between the frontend and Telegram.

    Dependencies are injected via the constructor to keep this class testable
    and decoupled from concrete infrastructure.
    """

    def __init__(
        self,
        message_repo: MessageRepository,
        chat_state_repo: ChatStateRepository,
        connection_manager: ConnectionManager,
        telegram_client: TelegramClient,
    ) -> None:
        self._message_repo = message_repo
        self._chat_state_repo = chat_state_repo
        self._connection_manager = connection_manager
        self._telegram_client = telegram_client

        # Serialises the "no active participant → assign this one" path.
        self._assign_lock = asyncio.Lock()

    # ── Inbound: Telegram → Frontend ─────────────────────────────────────────

    async def handle_telegram_message(self, chat_id: int, text: str) -> None:
        """Process a message received from Telegram and forward to the frontend.

        If no active participant has been set yet, this caller *becomes* the
        active participant.  Any other Telegram user is rejected with a polite
        message.
        """
        active_id = await self._resolve_active_participant(chat_id)
        if active_id is None:
            # _resolve_active_participant already sent the rejection notice.
            return

        sequence = await self._chat_state_repo.get_next_sequence()
        message = Message(
            id=generate_id(),
            text=text,
            direction="incoming",
            timestamp=utcnow_iso(),
            sequence=sequence,
        )

        await self._message_repo.add(message)

        event = MessageEvent(payload=message)
        await self._connection_manager.broadcast(event.model_dump())

        logger.info(
            "Telegram → Frontend | id=%s seq=%d chat_id=%d",
            message.id,
            sequence,
            chat_id,
        )

    # ── Outbound: Frontend → Telegram ────────────────────────────────────────

    async def handle_frontend_message(self, text: str) -> None:
        """Forward a message from the frontend to the active Telegram participant.

        If there is no active participant the message is silently dropped and
        a warning is logged.  The caller (WebSocket route) should surface an
        error to the frontend via the ErrorEvent envelope.
        """
        active_id = await self._chat_state_repo.get_active_chat_id()

        if active_id is None:
            logger.warning(
                "Frontend message dropped — no active Telegram participant"
            )
            return

        sequence = await self._chat_state_repo.get_next_sequence()
        message = Message(
            id=generate_id(),
            text=text,
            direction="outgoing",
            timestamp=utcnow_iso(),
            sequence=sequence,
        )

        await self._message_repo.add(message)
        await self._telegram_client.send_message(active_id, text)

        logger.info(
            "Frontend → Telegram | id=%s seq=%d chat_id=%d",
            message.id,
            sequence,
            active_id,
        )

    # ── State queries ─────────────────────────────────────────────────────────

    async def get_active_chat_id(self) -> Optional[int]:
        """Expose the current active participant ID for health/status endpoints."""
        return await self._chat_state_repo.get_active_chat_id()

    # ── Private helpers ───────────────────────────────────────────────────────

    async def _resolve_active_participant(self, chat_id: int) -> Optional[int]:
        """Determine whether *chat_id* may interact with the bot.

        Returns the confirmed active chat ID (which equals *chat_id* if this
        is the first caller), or None if the caller was rejected.

        The double-checked locking pattern protects against the race where two
        coroutines both read ``active_id == None`` before either writes.
        """
        # Optimistic read — avoids lock contention in the common case.
        active_id = await self._chat_state_repo.get_active_chat_id()

        if active_id is not None:
            if active_id != chat_id:
                logger.warning(
                    "Rejected Telegram message from chat_id=%d (active=%d)",
                    chat_id,
                    active_id,
                )
                await self._telegram_client.send_message(chat_id, REJECTED_MESSAGE)
                return None
            return active_id

        # Acquire the assignment lock and double-check.
        async with self._assign_lock:
            active_id = await self._chat_state_repo.get_active_chat_id()
            if active_id is None:
                await self._chat_state_repo.set_active_chat_id(chat_id)
                active_id = chat_id
                logger.info("Active Telegram participant assigned: chat_id=%d", chat_id)
            elif active_id != chat_id:
                await self._telegram_client.send_message(chat_id, REJECTED_MESSAGE)
                return None

        return active_id
