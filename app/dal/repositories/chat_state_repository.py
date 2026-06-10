from abc import ABC, abstractmethod
from typing import Optional


class ChatStateRepository(ABC):
    """Abstract contract for chat session state.

    Manages:
    - The single active Telegram chat ID (at most one at a time).
    - A monotonically increasing sequence counter for message ordering.

    All methods must be safe for concurrent async access.
    """

    @abstractmethod
    async def get_active_chat_id(self) -> Optional[int]:
        """Return the current active Telegram chat ID, or None if unset."""
        ...

    @abstractmethod
    async def set_active_chat_id(self, chat_id: int) -> None:
        """Assign a Telegram chat ID as the active participant."""
        ...

    @abstractmethod
    async def clear_active_chat_id(self) -> None:
        """Remove the active participant (reset to None)."""
        ...

    @abstractmethod
    async def get_next_sequence(self) -> int:
        """Atomically increment and return the next sequence number.

        Guaranteed to return unique, strictly increasing values even under
        concurrent access.
        """
        ...
