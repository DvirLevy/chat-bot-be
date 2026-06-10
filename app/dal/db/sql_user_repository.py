"""Postgres-backed implementation of ``UserRepository``."""

from typing import Optional

from sqlalchemy import func, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.dal.db.models import UserORM
from app.dal.repositories.user_repository import UserRepository
from app.models.user import User


class SqlUserRepository(UserRepository):
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    async def get_by_username(self, username: str) -> Optional[User]:
        async with self._session_factory() as session:
            row = await session.scalar(
                select(UserORM).where(UserORM.username == username)
            )
            return self._to_domain(row) if row is not None else None

    async def upsert(self, username: str) -> User:
        async with self._session_factory() as session:
            stmt = (
                pg_insert(UserORM)
                .values(username=username)
                .on_conflict_do_nothing(index_elements=["username"])
                .returning(UserORM)
            )
            result = await session.execute(stmt)
            row = result.scalar_one_or_none()
            if row is None:
                row = await session.scalar(
                    select(UserORM).where(UserORM.username == username)
                )
            await session.commit()
            return self._to_domain(row)

    async def set_chat_id(self, username: str, chat_id: int) -> None:
        async with self._session_factory() as session:
            await session.execute(
                update(UserORM)
                .where(UserORM.username == username)
                .values(telegram_chat_id=chat_id)
            )
            await session.commit()

    async def touch_last_active(self, username: str) -> None:
        async with self._session_factory() as session:
            await session.execute(
                update(UserORM)
                .where(UserORM.username == username)
                .values(last_active_at=func.now())
            )
            await session.commit()

    @staticmethod
    def _to_domain(row: UserORM) -> User:
        return User(
            username=row.username,
            telegram_chat_id=row.telegram_chat_id,
            created_at=row.created_at.isoformat(),
            last_active_at=row.last_active_at.isoformat() if row.last_active_at else None,
        )
