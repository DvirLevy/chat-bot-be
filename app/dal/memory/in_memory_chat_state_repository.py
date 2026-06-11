import asyncio
import time
from typing import Optional

from app.dal.repositories.chat_state_repository import ChatStateRepository


class InMemoryChatStateRepository(ChatStateRepository):
    """Thread-safe in-memory implementation of ChatStateRepository.

    A single asyncio.Lock protects all state fields so that a
    check-then-set pattern in the business layer can rely on the
    atomic helper methods here to avoid TOCTOU races.
    """

    def __init__(self) -> None:
        self._active_username: Optional[str] = None
        self._sequence_counter: int = 0
        self._last_activity: Optional[float] = None
        self._lock = asyncio.Lock()

    async def get_active_username(self) -> Optional[str]:
        async with self._lock:
            return self._active_username

    async def set_active_username(self, username: str) -> None:
        async with self._lock:
            self._active_username = username
            self._last_activity = time.monotonic()

    async def clear_active_username(self) -> None:
        async with self._lock:
            self._active_username = None
            self._last_activity = None

    async def get_next_sequence(self) -> int:
        """Atomically increment and return the sequence counter.

        Because the increment and read happen inside a single lock acquisition,
        two concurrent callers are guaranteed to receive different values in
        strict ascending order.
        """
        async with self._lock:
            self._sequence_counter += 1
            return self._sequence_counter

    async def touch_activity(self) -> None:
        async with self._lock:
            self._last_activity = time.monotonic()

    async def seconds_since_activity(self) -> Optional[float]:
        async with self._lock:
            if self._last_activity is None:
                return None
            return time.monotonic() - self._last_activity
