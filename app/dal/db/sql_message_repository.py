"""Postgres-backed implementation of ``MessageRepository``."""

from datetime import datetime
from typing import List

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.dal.db.models import MessageORM
from app.dal.repositories.message_repository import MessageRepository
from app.models.message import Message


class SqlMessageRepository(MessageRepository):
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    async def add(self, message: Message) -> None:
        async with self._session_factory() as session:
            session.add(self._to_orm(message))
            await session.commit()

    async def get_all(self) -> List[Message]:
        async with self._session_factory() as session:
            rows = await session.scalars(
                select(MessageORM).order_by(MessageORM.sequence)
            )
            return [self._to_domain(row) for row in rows]

    async def get_by_user(self, username: str) -> List[Message]:
        async with self._session_factory() as session:
            rows = await session.scalars(
                select(MessageORM)
                .where(MessageORM.username == username)
                .order_by(MessageORM.sequence)
            )
            return [self._to_domain(row) for row in rows]

    async def clear(self) -> None:
        async with self._session_factory() as session:
            await session.execute(delete(MessageORM))
            await session.commit()

    @staticmethod
    def _to_orm(message: Message) -> MessageORM:
        if message.username is None:
            raise ValueError("Message.username is required for SQL persistence")
        return MessageORM(
            id=message.id,
            username=message.username,
            text=message.text,
            direction=message.direction,
            timestamp=datetime.fromisoformat(message.timestamp),
            sequence=message.sequence,
        )

    @staticmethod
    def _to_domain(row: MessageORM) -> Message:
        return Message(
            id=row.id,
            text=row.text,
            direction=row.direction,
            timestamp=row.timestamp.isoformat(),
            sequence=row.sequence,
            username=row.username,
        )
