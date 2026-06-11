import asyncio
from typing import Dict, Optional

from app.dal.repositories.user_repository import UserRepository
from app.helpers.time_helper import utcnow_iso
from app.models.user import User


class InMemoryUserRepository(UserRepository):
    def __init__(self) -> None:
        self._users: Dict[str, User] = {}
        self._lock = asyncio.Lock()

    async def get_by_username(self, username: str) -> Optional[User]:
        async with self._lock:
            return self._users.get(username)

    async def upsert(self, username: str) -> User:
        async with self._lock:
            existing = self._users.get(username)
            if existing is not None:
                return existing
            user = User(username=username, created_at=utcnow_iso())
            self._users[username] = user
            return user

    async def set_chat_id(self, username: str, chat_id: int) -> None:
        async with self._lock:
            user = self._users[username]
            self._users[username] = user.model_copy(update={"telegram_chat_id": chat_id})

    async def touch_last_active(self, username: str) -> None:
        async with self._lock:
            user = self._users[username]
            self._users[username] = user.model_copy(update={"last_active_at": utcnow_iso()})
