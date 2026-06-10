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
    ``set_active_username`` call.  Without this lock two simultaneous
    ``assign_active_user`` calls arriving before either is persisted could
    both see ``active_username`` as None and both try to become the active
    participant.

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
from app.dal.repositories.user_repository import UserRepository
from app.helpers.id_helper import generate_id
from app.helpers.time_helper import utcnow_iso
from app.infrastructure.telegram.telegram_client import TelegramClient
from app.infrastructure.websocket.connection_manager import ConnectionManager
from app.models.message import Message
from app.models.websocket_events import IdleTimeoutEvent, MessageEvent

logger = logging.getLogger("chatbot.service")


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
        user_repo: UserRepository,
        idle_timeout_seconds: int = 300,
    ) -> None:
        self._message_repo = message_repo
        self._chat_state_repo = chat_state_repo
        self._connection_manager = connection_manager
        self._telegram_client = telegram_client
        self._user_repo = user_repo
        self._idle_timeout_seconds = idle_timeout_seconds

        # Serialises the "no active participant → assign this one" path.
        self._assign_lock = asyncio.Lock()

    # ── Active participant management ────────────────────────────────────────

    async def assign_active_user(self, username: str) -> bool:
        """Try to make *username* the active participant.

        Returns True if *username* is (or becomes) the active participant,
        or False if another user is already active (busy).

        The double-checked locking pattern protects against the race where
        two coroutines both read ``active_username == None`` before either
        writes.
        """
        await self._user_repo.upsert(username)

        active_username = await self._chat_state_repo.get_active_username()
        if active_username is not None:
            if active_username == username:
                await self._chat_state_repo.touch_activity()
                return True
            return False

        async with self._assign_lock:
            active_username = await self._chat_state_repo.get_active_username()
            if active_username is None:
                await self._chat_state_repo.set_active_username(username)
                logger.info("Active participant assigned: username=%s", username)
                return True
            if active_username == username:
                await self._chat_state_repo.touch_activity()
                return True
            return False

    async def release_active(self) -> None:
        """Clear the active participant, freeing the slot for the next user."""
        await self._chat_state_repo.clear_active_username()
        logger.info("Active participant released")

    async def get_active_username(self) -> Optional[str]:
        """Expose the current active participant for health/status endpoints."""
        return await self._chat_state_repo.get_active_username()

    # ── Idle-timeout ─────────────────────────────────────────────────────────

    async def release_idle_session(self) -> Optional[str]:
        """Release the active participant if idle past the configured timeout.

        Returns the released username, or None if nothing was released.
        """
        active_username = await self._chat_state_repo.get_active_username()
        if active_username is None:
            return None

        idle_seconds = await self._chat_state_repo.seconds_since_activity()
        if idle_seconds is None or idle_seconds < self._idle_timeout_seconds:
            return None

        await self._chat_state_repo.clear_active_username()
        logger.info(
            "Active participant released due to inactivity: username=%s (idle %.1fs)",
            active_username,
            idle_seconds,
        )

        event = IdleTimeoutEvent(username=active_username)
        await self._connection_manager.broadcast(event.model_dump())

        return active_username

    async def run_idle_timeout_checker(self, check_interval_seconds: float = 5.0) -> None:
        """Background loop: periodically release the active participant if idle.

        Intended to run as a long-lived asyncio.Task for the application's
        lifetime; cancel it during shutdown.
        """
        while True:
            await asyncio.sleep(check_interval_seconds)
            await self.release_idle_session()

    # ── Inbound: Telegram → Frontend ─────────────────────────────────────────

    async def handle_telegram_message(self, chat_id: int, text: str) -> None:
        """Process a message received from Telegram and forward to the frontend.

        The message is attributed to the active participant.  On the active
        participant's first Telegram message, *chat_id* is linked to their
        username and persisted.  Messages from any other chat_id are dropped
        (busy) without sending a reply.
        """
        active_username = await self._chat_state_repo.get_active_username()
        if active_username is None:
            logger.warning(
                "Telegram message dropped — no active participant (chat_id=%d)",
                chat_id,
            )
            return

        user = await self._user_repo.get_by_username(active_username)
        if user is None:
            logger.warning(
                "Telegram message dropped — active username=%s has no user record",
                active_username,
            )
            return

        if user.telegram_chat_id is None:
            await self._user_repo.set_chat_id(active_username, chat_id)
            logger.info(
                "Linked Telegram chat_id=%d to username=%s", chat_id, active_username
            )
        elif user.telegram_chat_id != chat_id:
            logger.warning(
                "Rejected Telegram message from chat_id=%d (busy with username=%s)",
                chat_id,
                active_username,
            )
            return

        await self._chat_state_repo.touch_activity()

        sequence = await self._chat_state_repo.get_next_sequence()
        message = Message(
            id=generate_id(),
            text=text,
            direction="incoming",
            timestamp=utcnow_iso(),
            sequence=sequence,
            username=active_username,
        )

        await self._message_repo.add(message)

        event = MessageEvent(payload=message)
        await self._connection_manager.broadcast(event.model_dump())

        logger.info(
            "Telegram → Frontend | id=%s seq=%d username=%s",
            message.id,
            sequence,
            active_username,
        )

    # ── Outbound: Frontend → Telegram ────────────────────────────────────────

    async def handle_frontend_message(self, text: str, username: str) -> None:
        """Forward a message from *username* to their linked Telegram chat.

        If *username* has no linked ``telegram_chat_id`` yet, the message is
        stored but cannot be delivered to Telegram — a warning is logged.
        """
        active_username = await self._chat_state_repo.get_active_username()
        if active_username == username:
            await self._chat_state_repo.touch_activity()

        sequence = await self._chat_state_repo.get_next_sequence()
        message = Message(
            id=generate_id(),
            text=text,
            direction="outgoing",
            timestamp=utcnow_iso(),
            sequence=sequence,
            username=username,
        )

        await self._message_repo.add(message)

        user = await self._user_repo.get_by_username(username)
        if user is None or user.telegram_chat_id is None:
            logger.warning(
                "Frontend message stored but not delivered — no Telegram chat "
                "linked for username=%s",
                username,
            )
            return

        await self._telegram_client.send_message(user.telegram_chat_id, text)

        logger.info(
            "Frontend → Telegram | id=%s seq=%d username=%s chat_id=%d",
            message.id,
            sequence,
            username,
            user.telegram_chat_id,
        )
