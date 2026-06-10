"""
Tests for core ChatService behaviour: routing, storage, and broadcast.
"""

import pytest

from app.bl.chat_service import ChatService
from app.models.message import Message


@pytest.mark.asyncio
async def test_first_telegram_message_sets_active_participant(
    chat_service: ChatService,
) -> None:
    await chat_service.handle_telegram_message(chat_id=100, text="Hello")

    active = await chat_service.get_active_chat_id()
    assert active == 100


@pytest.mark.asyncio
async def test_incoming_message_is_stored(
    chat_service: ChatService,
    message_repo,
) -> None:
    await chat_service.handle_telegram_message(chat_id=1, text="Stored message")

    messages = await message_repo.get_all()
    assert len(messages) == 1
    assert messages[0].text == "Stored message"
    assert messages[0].direction == "incoming"


@pytest.mark.asyncio
async def test_incoming_message_is_broadcast_to_frontend(
    chat_service: ChatService,
    mock_connection_manager,
) -> None:
    await chat_service.handle_telegram_message(chat_id=1, text="Broadcast me")

    mock_connection_manager.broadcast.assert_awaited_once()
    call_kwargs = mock_connection_manager.broadcast.call_args[0][0]
    assert call_kwargs["type"] == "message"
    assert call_kwargs["payload"]["text"] == "Broadcast me"
    assert call_kwargs["payload"]["direction"] == "incoming"


@pytest.mark.asyncio
async def test_outgoing_message_sent_to_telegram(
    chat_service: ChatService,
    mock_telegram_client,
) -> None:
    # Establish an active participant first.
    await chat_service.handle_telegram_message(chat_id=42, text="Hi from Telegram")
    mock_telegram_client.send_message.reset_mock()

    await chat_service.handle_frontend_message("Reply from frontend")

    mock_telegram_client.send_message.assert_awaited_once_with(42, "Reply from frontend")


@pytest.mark.asyncio
async def test_outgoing_message_is_stored(
    chat_service: ChatService,
    message_repo,
) -> None:
    await chat_service.handle_telegram_message(chat_id=5, text="Setup")
    await chat_service.handle_frontend_message("Frontend reply")

    messages = await message_repo.get_all()
    outgoing = [m for m in messages if m.direction == "outgoing"]
    assert len(outgoing) == 1
    assert outgoing[0].text == "Frontend reply"


@pytest.mark.asyncio
async def test_frontend_message_dropped_when_no_active_participant(
    chat_service: ChatService,
    mock_telegram_client,
    message_repo,
) -> None:
    await chat_service.handle_frontend_message("No one home")

    mock_telegram_client.send_message.assert_not_awaited()
    messages = await message_repo.get_all()
    assert len(messages) == 0


@pytest.mark.asyncio
async def test_message_has_required_fields(
    chat_service: ChatService,
    mock_connection_manager,
) -> None:
    await chat_service.handle_telegram_message(chat_id=7, text="Field check")

    payload: dict = mock_connection_manager.broadcast.call_args[0][0]["payload"]
    assert "id" in payload
    assert "text" in payload
    assert "direction" in payload
    assert "timestamp" in payload
    assert "sequence" in payload


@pytest.mark.asyncio
async def test_message_id_is_unique(
    chat_service: ChatService,
    message_repo,
) -> None:
    await chat_service.handle_telegram_message(chat_id=1, text="A")
    await chat_service.handle_telegram_message(chat_id=1, text="B")

    messages = await message_repo.get_all()
    ids = [m.id for m in messages]
    assert len(ids) == len(set(ids)), "Message IDs must be unique"
