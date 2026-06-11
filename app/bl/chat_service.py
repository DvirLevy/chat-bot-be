import asyncio
import logging
from typing import List, Optional

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

        self._assign_lock = asyncio.Lock()

    async def assign_active_user(self, username: str) -> bool:
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
        await self._chat_state_repo.clear_active_username()
        logger.info("Active participant released")

    async def release_active_if(self, username: str) -> None:
        active_username = await self._chat_state_repo.get_active_username()
        if active_username == username:
            await self._chat_state_repo.clear_active_username()
            logger.info("Active participant released: username=%s", username)

    async def get_active_username(self) -> Optional[str]:
        return await self._chat_state_repo.get_active_username()

    async def release_idle_session(self) -> Optional[str]:
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
        while True:
            await asyncio.sleep(check_interval_seconds)
            await self.release_idle_session()

    async def get_history(self, username: str) -> List[Message]:
        return await self._message_repo.get_by_user(username)

    async def handle_telegram_message(self, chat_id: int, text: str) -> None:
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

    async def handle_frontend_message(self, text: str, username: str) -> None:
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

        await self._telegram_client.send_message(user.telegram_chat_id, f"{username}: {text}")

        logger.info(
            "Frontend → Telegram | id=%s seq=%d username=%s chat_id=%d",
            message.id,
            sequence,
            username,
            user.telegram_chat_id,
        )
