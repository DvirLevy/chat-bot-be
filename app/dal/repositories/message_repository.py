from abc import ABC, abstractmethod
from typing import List

from app.models.message import Message


class MessageRepository(ABC):

    @abstractmethod
    async def add(self, message: Message) -> None:
        ...

    @abstractmethod
    async def get_all(self) -> List[Message]:
        ...

    @abstractmethod
    async def get_by_user(self, username: str) -> List[Message]:
        ...

    @abstractmethod
    async def clear(self) -> None:
        ...
