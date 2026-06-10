import pytest

from app.dal.memory.in_memory_message_repository import InMemoryMessageRepository
from app.helpers.id_helper import generate_id
from app.helpers.time_helper import utcnow_iso
from app.models.message import Message


@pytest.fixture
def repo() -> InMemoryMessageRepository:
    return InMemoryMessageRepository()


def _make_message(username: str, sequence: int, text: str = "hi") -> Message:
    return Message(
        id=generate_id(),
        text=text,
        direction="incoming",
        timestamp=utcnow_iso(),
        sequence=sequence,
        username=username,
    )


async def test_messages_are_saved_with_username(repo: InMemoryMessageRepository) -> None:
    await repo.add(_make_message("alice", sequence=1))

    messages = await repo.get_all()
    assert messages[0].username == "alice"


async def test_get_by_user_returns_only_that_users_messages_sorted(
    repo: InMemoryMessageRepository,
) -> None:
    await repo.add(_make_message("alice", sequence=2, text="second"))
    await repo.add(_make_message("bob", sequence=3, text="bob's message"))
    await repo.add(_make_message("alice", sequence=1, text="first"))

    alice_messages = await repo.get_by_user("alice")

    assert [m.text for m in alice_messages] == ["first", "second"]
    assert all(m.username == "alice" for m in alice_messages)


async def test_get_by_user_returns_empty_list_for_unknown_user(
    repo: InMemoryMessageRepository,
) -> None:
    assert await repo.get_by_user("ghost") == []
