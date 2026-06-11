from abc import ABC, abstractmethod
from typing import Optional

from app.models.user import User


class UserRepository(ABC):

    @abstractmethod
    async def get_by_username(self, username: str) -> Optional[User]:
        ...

    @abstractmethod
    async def upsert(self, username: str) -> User:
        ...

    @abstractmethod
    async def set_chat_id(self, username: str, chat_id: int) -> None:
        ...

    @abstractmethod
    async def touch_last_active(self, username: str) -> None:
        ...
