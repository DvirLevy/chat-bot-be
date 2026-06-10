from abc import ABC, abstractmethod
from typing import Optional


class ChatStateRepository(ABC):
    """Abstract contract for chat session state.

    Manages:
    - The single active participant, identified by frontend ``username``.
    - A monotonically increasing sequence counter for message ordering.

    All methods must be safe for concurrent async access.
    """

    @abstractmethod
    async def get_active_username(self) -> Optional[str]:
        """Return the current active participant's username, or None if unset."""
        ...

    @abstractmethod
    async def set_active_username(self, username: str) -> None:
        """Assign *username* as the active participant."""
        ...

    @abstractmethod
    async def clear_active_username(self) -> None:
        """Remove the active participant (reset to None)."""
        ...

    @abstractmethod
    async def get_next_sequence(self) -> int:
        """Atomically increment and return the next sequence number.

        Guaranteed to return unique, strictly increasing values even under
        concurrent access.
        """
        ...
