"""
Tests for idle-timeout: inactivity releases the active participant and
notifies the frontend.
"""

import asyncio

import pytest

from app.bl.chat_service import ChatService
from app.dal.memory.in_memory_chat_state_repository import InMemoryChatStateRepository
from app.dal.memory.in_memory_message_repository import InMemoryMessageRepository
from app.dal.memory.in_memory_user_repository import InMemoryUserRepository


@pytest.fixture
def idle_chat_service(mock_connection_manager, mock_telegram_client) -> ChatService:
    """A ChatService with an effectively-zero idle timeout for fast tests."""
    return ChatService(
        message_repo=InMemoryMessageRepository(),
        chat_state_repo=InMemoryChatStateRepository(),
        connection_manager=mock_connection_manager,
        telegram_client=mock_telegram_client,
        user_repo=InMemoryUserRepository(),
        idle_timeout_seconds=0,
    )


@pytest.mark.asyncio
async def test_no_release_when_no_active_user(idle_chat_service: ChatService) -> None:
    released = await idle_chat_service.release_idle_session()
    assert released is None


@pytest.mark.asyncio
async def test_no_release_before_timeout_elapses(chat_service: ChatService) -> None:
    """With the default (non-zero) timeout, a fresh session is not idle."""
    await chat_service.assign_active_user("alice")

    released = await chat_service.release_idle_session()
    assert released is None
    assert await chat_service.get_active_username() == "alice"


@pytest.mark.asyncio
async def test_idle_session_is_released_and_notified(
    idle_chat_service: ChatService,
    mock_connection_manager,
) -> None:
    await idle_chat_service.assign_active_user("alice")
    await asyncio.sleep(0.01)  # ensure idle_seconds > 0 (timeout is 0)

    released = await idle_chat_service.release_idle_session()

    assert released == "alice"
    assert await idle_chat_service.get_active_username() is None

    mock_connection_manager.broadcast.assert_awaited_once()
    event = mock_connection_manager.broadcast.call_args[0][0]
    assert event["type"] == "idle_timeout"
    assert event["username"] == "alice"


@pytest.mark.asyncio
async def test_activity_resets_idle_timer(
    mock_connection_manager,
    mock_telegram_client,
) -> None:
    chat_service = ChatService(
        message_repo=InMemoryMessageRepository(),
        chat_state_repo=InMemoryChatStateRepository(),
        connection_manager=mock_connection_manager,
        telegram_client=mock_telegram_client,
        user_repo=InMemoryUserRepository(),
        idle_timeout_seconds=10,
    )

    await chat_service.assign_active_user("alice")
    await chat_service.handle_telegram_message(chat_id=1, text="hi")

    released = await chat_service.release_idle_session()
    assert released is None
    assert await chat_service.get_active_username() == "alice"


@pytest.mark.asyncio
async def test_release_active_allows_next_user_after_idle(
    idle_chat_service: ChatService,
) -> None:
    await idle_chat_service.assign_active_user("alice")
    await asyncio.sleep(0.01)
    await idle_chat_service.release_idle_session()

    assigned = await idle_chat_service.assign_active_user("bob")
    assert assigned is True
    assert await idle_chat_service.get_active_username() == "bob"
