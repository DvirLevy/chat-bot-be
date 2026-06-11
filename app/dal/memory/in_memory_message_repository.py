import asyncio
from typing import List

from app.dal.repositories.message_repository import MessageRepository
from app.models.message import Message


class InMemoryMessageRepository(MessageRepository):
    """Thread-safe in-memory implementation of MessageRepository.

    Uses an asyncio.Lock to serialise mutations so that concurrent coroutines
    cannot observe a partially-updated list.
    """

    def __init__(self) -> None:
        self._messages: List[Message] = []
        self._lock = asyncio.Lock()

    async def add(self, message: Message) -> None:
        async with self._lock:
            self._messages.append(message)

    async def get_all(self) -> List[Message]:
        async with self._lock:
            # Return a shallow copy so callers cannot mutate the internal list.
            return list(self._messages)

    async def get_by_user(self, username: str) -> List[Message]:
        async with self._lock:
            return sorted(
                (m for m in self._messages if m.username == username),
                key=lambda m: m.sequence,
            )

    async def clear(self) -> None:
        async with self._lock:
            self._messages.clear()
