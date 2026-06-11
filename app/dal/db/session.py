"""Async engine and session-factory helpers.

The application creates exactly one engine for its lifetime (in the FastAPI
``lifespan``) and shares an ``async_sessionmaker`` via ``app.state``.  SQL
repositories (BE-2, BE-3) open a short-lived ``AsyncSession`` per operation.
"""

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)


def create_engine(database_url: str, *, echo: bool = False) -> AsyncEngine:
    """Create the async engine for *database_url*.

    ``pool_pre_ping`` guards against stale connections after the database
    restarts or idle timeouts close sockets.
    """
    return create_async_engine(
        database_url,
        echo=echo,
        pool_pre_ping=True,
    )


def create_session_factory(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    """Build a session factory bound to *engine*.

    ``expire_on_commit=False`` lets callers keep using ORM objects after commit
    without triggering lazy reloads.
    """
    return async_sessionmaker(
        bind=engine,
        class_=AsyncSession,
        expire_on_commit=False,
        autoflush=False,
    )
