from typing import Optional

from pydantic import BaseModel, Field


class User(BaseModel):

    username: str = Field(..., description="Frontend participant identifier")
    telegram_chat_id: Optional[int] = Field(
        default=None,
        description=(
            "Linked Telegram chat ID; None until the user's first Telegram "
            "message binds it"
        ),
    )
    created_at: str = Field(..., description="ISO-8601 UTC timestamp")
    last_active_at: Optional[str] = Field(
        default=None, description="ISO-8601 UTC timestamp"
    )
