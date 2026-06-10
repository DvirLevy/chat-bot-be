import asyncio
from typing import Optional

from app.dal.repositories.chat_state_repository import ChatStateRepository


class InMemoryChatStateRepository(ChatStateRepository):
    """Thread-safe in-memory implementation of ChatStateRepository.

    A single asyncio.Lock protects all state fields so that a
    check-then-set pattern in the business layer can rely on the
    atomic helper methods here to avoid TOCTOU races.
    """

    def __init__(self) -> None:
        self._active_chat_id: Optional[int] = None
        self._sequence_counter: int = 0
        self._lock = asyncio.Lock()

    async def get_active_chat_id(self) -> Optional[int]:
        async with self._lock:
            return self._active_chat_id

    async def set_active_chat_id(self, chat_id: int) -> None:
        async with self._lock:
            self._active_chat_id = chat_id

    async def clear_active_chat_id(self) -> None:
        async with self._lock:
            self._active_chat_id = None

    async def get_next_sequence(self) -> int:
        """Atomically increment and return the sequence counter.

        Because the increment and read happen inside a single lock acquisition,
        two concurrent callers are guaranteed to receive different values in
        strict ascending order.
        """
        async with self._lock:
            self._sequence_counter += 1
            return self._sequence_counter
