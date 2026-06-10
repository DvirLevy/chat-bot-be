"""
Tests that verify message sequence number correctness and uniqueness.
"""

import asyncio

import pytest

from app.bl.chat_service import ChatService


@pytest.mark.asyncio
async def test_sequences_are_strictly_increasing(
    chat_service: ChatService,
    message_repo,
) -> None:
    for text in ("first", "second", "third"):
        await chat_service.handle_telegram_message(chat_id=1, text=text)

    messages = await message_repo.get_all()
    sequences = [m.sequence for m in messages]
    assert sequences == sorted(sequences), "Sequences must be in ascending order"


@pytest.mark.asyncio
async def test_sequences_start_at_one(
    chat_service: ChatService,
    message_repo,
) -> None:
    await chat_service.handle_telegram_message(chat_id=1, text="first")
    messages = await message_repo.get_all()
    assert messages[0].sequence == 1


@pytest.mark.asyncio
async def test_sequences_are_unique(
    chat_service: ChatService,
    message_repo,
) -> None:
    for i in range(10):
        await chat_service.handle_telegram_message(chat_id=1, text=f"msg {i}")

    messages = await message_repo.get_all()
    sequences = [m.sequence for m in messages]
    assert len(sequences) == len(set(sequences)), "All sequence numbers must be unique"


@pytest.mark.asyncio
async def test_mixed_direction_sequences_are_unique(
    chat_service: ChatService,
    message_repo,
) -> None:
    """Outgoing and incoming messages share the same counter — all must be unique."""
    await chat_service.handle_telegram_message(chat_id=1, text="from telegram")
    await chat_service.handle_frontend_message("from frontend")
    await chat_service.handle_telegram_message(chat_id=1, text="from telegram 2")

    messages = await message_repo.get_all()
    sequences = [m.sequence for m in messages]
    assert len(sequences) == len(set(sequences))


@pytest.mark.asyncio
async def test_concurrent_messages_have_unique_sequences(
    chat_service: ChatService,
    message_repo,
) -> None:
    """Fire 20 messages concurrently; each must receive a unique sequence number."""
    # Establish active participant.
    await chat_service.handle_telegram_message(chat_id=1, text="setup")
    await message_repo.clear()

    tasks = [
        chat_service.handle_telegram_message(chat_id=1, text=f"concurrent {i}")
        for i in range(20)
    ]
    await asyncio.gather(*tasks)

    messages = await message_repo.get_all()
    assert len(messages) == 20

    sequences = [m.sequence for m in messages]
    assert len(sequences) == len(set(sequences)), (
        "Concurrent messages must have unique sequence numbers"
    )


@pytest.mark.asyncio
async def test_broadcast_payload_contains_sequence(
    chat_service: ChatService,
    mock_connection_manager,
) -> None:
    await chat_service.handle_telegram_message(chat_id=1, text="check seq field")

    payload = mock_connection_manager.broadcast.call_args[0][0]["payload"]
    assert isinstance(payload["sequence"], int)
    assert payload["sequence"] >= 1
