from abc import ABC, abstractmethod
from typing import List

from app.models.message import Message


class MessageRepository(ABC):
    """Abstract contract for message persistence.

    Implementations must be safe for concurrent async access.
    """

    @abstractmethod
    async def add(self, message: Message) -> None:
        """Persist a single message."""
        ...

    @abstractmethod
    async def get_all(self) -> List[Message]:
        """Return all messages in insertion order."""
        ...

    @abstractmethod
    async def clear(self) -> None:
        """Remove all stored messages."""
        ...
