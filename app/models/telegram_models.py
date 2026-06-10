from typing import Optional

from pydantic import BaseModel


class TelegramUser(BaseModel):
    """Lightweight representation of a Telegram user."""

    id: int
    username: Optional[str] = None
    first_name: Optional[str] = None
    last_name: Optional[str] = None
