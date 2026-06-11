"""Abstract contract for user/participant persistence."""

from abc import ABC, abstractmethod
from typing import Optional

from app.models.user import User


class UserRepository(ABC):
    """Abstract repository for ``User`` records.

    Implementations must be safe for concurrent async access.
    """

    @abstractmethod
    async def get_by_username(self, username: str) -> Optional[User]:
        """Return the user with *username*, or ``None`` if not found."""
        ...

    @abstractmethod
    async def upsert(self, username: str) -> User:
        """Return the existing user with *username*, creating it if missing."""
        ...

    @abstractmethod
    async def set_chat_id(self, username: str, chat_id: int) -> None:
        """Bind a Telegram chat ID to the user identified by *username*."""
        ...

    @abstractmethod
    async def touch_last_active(self, username: str) -> None:
        """Update ``last_active_at`` for *username* to the current time."""
        ...
