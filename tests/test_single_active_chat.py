"""
Tests that enforce the single-active-participant constraint.
"""

import pytest

from app.bl.chat_service import REJECTED_MESSAGE, ChatService


@pytest.mark.asyncio
async def test_first_sender_becomes_active(chat_service: ChatService) -> None:
    await chat_service.handle_telegram_message(chat_id=111, text="First")

    assert await chat_service.get_active_chat_id() == 111


@pytest.mark.asyncio
async def test_second_sender_is_rejected(
    chat_service: ChatService,
    mock_telegram_client,
) -> None:
    await chat_service.handle_telegram_message(chat_id=111, text="First")
    await chat_service.handle_telegram_message(chat_id=222, text="Second")

    mock_telegram_client.send_message.assert_awaited_once_with(222, REJECTED_MESSAGE)


@pytest.mark.asyncio
async def test_second_sender_message_not_broadcast(
    chat_service: ChatService,
    mock_connection_manager,
) -> None:
    await chat_service.handle_telegram_message(chat_id=111, text="First")
    mock_connection_manager.broadcast.reset_mock()

    await chat_service.handle_telegram_message(chat_id=222, text="Intruder")

    mock_connection_manager.broadcast.assert_not_awaited()


@pytest.mark.asyncio
async def test_second_sender_message_not_stored(
    chat_service: ChatService,
    message_repo,
) -> None:
    await chat_service.handle_telegram_message(chat_id=111, text="First")
    await chat_service.handle_telegram_message(chat_id=222, text="Intruder")

    messages = await message_repo.get_all()
    texts = [m.text for m in messages]
    assert "Intruder" not in texts


@pytest.mark.asyncio
async def test_active_sender_not_rejected(
    chat_service: ChatService,
    mock_telegram_client,
) -> None:
    await chat_service.handle_telegram_message(chat_id=111, text="First")
    await chat_service.handle_telegram_message(chat_id=111, text="Second from same user")

    mock_telegram_client.send_message.assert_not_awaited()


@pytest.mark.asyncio
async def test_active_participant_persists_across_multiple_messages(
    chat_service: ChatService,
) -> None:
    for i in range(5):
        await chat_service.handle_telegram_message(chat_id=999, text=f"msg {i}")

    assert await chat_service.get_active_chat_id() == 999


@pytest.mark.asyncio
async def test_third_sender_also_rejected(
    chat_service: ChatService,
    mock_telegram_client,
) -> None:
    await chat_service.handle_telegram_message(chat_id=1, text="Owner")
    await chat_service.handle_telegram_message(chat_id=2, text="Intruder 1")
    await chat_service.handle_telegram_message(chat_id=3, text="Intruder 2")

    rejection_calls = [
        call
        for call in mock_telegram_client.send_message.await_args_list
        if call.args[1] == REJECTED_MESSAGE
    ]
    rejected_ids = {call.args[0] for call in rejection_calls}
    assert 2 in rejected_ids
    assert 3 in rejected_ids
