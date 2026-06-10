from abc import ABC, abstractmethod
from typing import Optional


class ChatStateRepository(ABC):
    """Abstract contract for chat session state.

    Manages:
    - The single active participant, identified by frontend ``username``.
    - A monotonically increasing sequence counter for message ordering.
    - The last-activity timestamp for the active session (idle-timeout).

    All methods must be safe for concurrent async access.
    """

    @abstractmethod
    async def get_active_username(self) -> Optional[str]:
        """Return the current active participant's username, or None if unset."""
        ...

    @abstractmethod
    async def set_active_username(self, username: str) -> None:
        """Assign *username* as the active participant.

        Also marks the session as active now (see ``touch_activity``).
        """
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

    @abstractmethod
    async def touch_activity(self) -> None:
        """Record that activity occurred now, for idle-timeout tracking."""
        ...

    @abstractmethod
    async def seconds_since_activity(self) -> Optional[float]:
        """Return seconds elapsed since the last recorded activity.

        Returns None if no activity has been recorded (e.g. no active
        participant yet).
        """
        ...
