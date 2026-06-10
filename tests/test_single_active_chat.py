"""
Tests that enforce the single-active-participant constraint, using the
username-based active model.
"""

import pytest

from app.bl.chat_service import ChatService


@pytest.mark.asyncio
async def test_first_user_becomes_active(chat_service: ChatService) -> None:
    assigned = await chat_service.assign_active_user("alice")

    assert assigned is True
    assert await chat_service.get_active_username() == "alice"


@pytest.mark.asyncio
async def test_second_user_is_rejected(chat_service: ChatService) -> None:
    await chat_service.assign_active_user("alice")

    assigned = await chat_service.assign_active_user("bob")

    assert assigned is False
    assert await chat_service.get_active_username() == "alice"


@pytest.mark.asyncio
async def test_second_user_rejection_does_not_send_telegram_message(
    chat_service: ChatService,
    mock_telegram_client,
) -> None:
    await chat_service.assign_active_user("alice")

    await chat_service.assign_active_user("bob")

    mock_telegram_client.send_message.assert_not_awaited()


@pytest.mark.asyncio
async def test_active_user_reassignment_succeeds(chat_service: ChatService) -> None:
    await chat_service.assign_active_user("alice")

    assigned = await chat_service.assign_active_user("alice")

    assert assigned is True
    assert await chat_service.get_active_username() == "alice"


@pytest.mark.asyncio
async def test_chat_id_links_to_active_user_on_first_telegram_message(
    chat_service: ChatService,
    user_repo,
) -> None:
    await chat_service.assign_active_user("alice")

    await chat_service.handle_telegram_message(chat_id=111, text="Hello")

    user = await user_repo.get_by_username("alice")
    assert user.telegram_chat_id == 111


@pytest.mark.asyncio
async def test_message_from_unlinked_chat_id_is_rejected(
    chat_service: ChatService,
    message_repo,
) -> None:
    await chat_service.assign_active_user("alice")
    await chat_service.handle_telegram_message(chat_id=111, text="First")

    await chat_service.handle_telegram_message(chat_id=222, text="Intruder")

    messages = await message_repo.get_all()
    texts = [m.text for m in messages]
    assert "Intruder" not in texts


@pytest.mark.asyncio
async def test_message_from_unlinked_chat_id_not_broadcast(
    chat_service: ChatService,
    mock_connection_manager,
) -> None:
    await chat_service.assign_active_user("alice")
    await chat_service.handle_telegram_message(chat_id=111, text="First")
    mock_connection_manager.broadcast.reset_mock()

    await chat_service.handle_telegram_message(chat_id=222, text="Intruder")

    mock_connection_manager.broadcast.assert_not_awaited()


@pytest.mark.asyncio
async def test_message_dropped_when_no_active_user(
    chat_service: ChatService,
    message_repo,
) -> None:
    await chat_service.handle_telegram_message(chat_id=111, text="Nobody home")

    messages = await message_repo.get_all()
    assert messages == []


@pytest.mark.asyncio
async def test_release_active_allows_next_user(chat_service: ChatService) -> None:
    await chat_service.assign_active_user("alice")

    await chat_service.release_active()

    assert await chat_service.get_active_username() is None
    assigned = await chat_service.assign_active_user("bob")
    assert assigned is True
    assert await chat_service.get_active_username() == "bob"


@pytest.mark.asyncio
async def test_chat_id_link_persists_across_release(
    chat_service: ChatService,
    user_repo,
) -> None:
    await chat_service.assign_active_user("alice")
    await chat_service.handle_telegram_message(chat_id=111, text="First")

    await chat_service.release_active()

    user = await user_repo.get_by_username("alice")
    assert user.telegram_chat_id == 111
