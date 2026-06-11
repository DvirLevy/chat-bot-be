"""
Shared pytest fixtures.

All async fixtures use the ``asyncio`` backend via the ``pytest-asyncio``
``asyncio_mode = "auto"`` setting in ``pytest.ini``.
"""

from unittest.mock import AsyncMock, MagicMock

import pytest

from app.bl.chat_service import ChatService
from app.dal.memory.in_memory_chat_state_repository import InMemoryChatStateRepository
from app.dal.memory.in_memory_message_repository import InMemoryMessageRepository
from app.dal.memory.in_memory_user_repository import InMemoryUserRepository


@pytest.fixture
def mock_connection_manager() -> MagicMock:
    manager = MagicMock()
    manager.broadcast = AsyncMock()
    return manager


@pytest.fixture
def mock_telegram_client() -> MagicMock:
    client = MagicMock()
    client.send_message = AsyncMock()
    return client


@pytest.fixture
def message_repo() -> InMemoryMessageRepository:
    return InMemoryMessageRepository()


@pytest.fixture
def chat_state_repo() -> InMemoryChatStateRepository:
    return InMemoryChatStateRepository()


@pytest.fixture
def user_repo() -> InMemoryUserRepository:
    return InMemoryUserRepository()


@pytest.fixture
def chat_service(
    message_repo: InMemoryMessageRepository,
    chat_state_repo: InMemoryChatStateRepository,
    mock_connection_manager: MagicMock,
    mock_telegram_client: MagicMock,
    user_repo: InMemoryUserRepository,
) -> ChatService:
    return ChatService(
        message_repo=message_repo,
        chat_state_repo=chat_state_repo,
        connection_manager=mock_connection_manager,
        telegram_client=mock_telegram_client,
        user_repo=user_repo,
    )
