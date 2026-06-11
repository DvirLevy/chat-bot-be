from abc import ABC, abstractmethod
from typing import Optional


class ChatStateRepository(ABC):

    @abstractmethod
    async def get_active_username(self) -> Optional[str]:
        ...

    @abstractmethod
    async def set_active_username(self, username: str) -> None:
        ...

    @abstractmethod
    async def clear_active_username(self) -> None:
        ...

    @abstractmethod
    async def get_next_sequence(self) -> int:
        ...

    @abstractmethod
    async def touch_activity(self) -> None:
        ...

    @abstractmethod
    async def seconds_since_activity(self) -> Optional[float]:
        ...
