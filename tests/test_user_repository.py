import pytest

from app.dal.memory.in_memory_user_repository import InMemoryUserRepository


@pytest.fixture
def user_repo() -> InMemoryUserRepository:
    return InMemoryUserRepository()


async def test_upsert_then_get_returns_same_user(user_repo: InMemoryUserRepository) -> None:
    created = await user_repo.upsert("alice")

    fetched = await user_repo.get_by_username("alice")

    assert fetched == created
    assert fetched.username == "alice"
    assert fetched.telegram_chat_id is None


async def test_upsert_is_idempotent(user_repo: InMemoryUserRepository) -> None:
    first = await user_repo.upsert("alice")
    second = await user_repo.upsert("alice")

    assert first == second


async def test_set_chat_id_persists(user_repo: InMemoryUserRepository) -> None:
    await user_repo.upsert("alice")

    await user_repo.set_chat_id("alice", 12345)

    fetched = await user_repo.get_by_username("alice")
    assert fetched is not None
    assert fetched.telegram_chat_id == 12345


async def test_touch_last_active_sets_timestamp(user_repo: InMemoryUserRepository) -> None:
    await user_repo.upsert("alice")
    assert (await user_repo.get_by_username("alice")).last_active_at is None

    await user_repo.touch_last_active("alice")

    fetched = await user_repo.get_by_username("alice")
    assert fetched is not None
    assert fetched.last_active_at is not None


async def test_get_by_username_returns_none_for_unknown_user(
    user_repo: InMemoryUserRepository,
) -> None:
    assert await user_repo.get_by_username("ghost") is None
