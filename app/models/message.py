from typing import Literal, Optional

from pydantic import BaseModel, Field


class Message(BaseModel):

    id: str = Field(..., description="UUID string")
    text: str = Field(..., description="Message body")
    direction: Literal["incoming", "outgoing"] = Field(
        ...,
        description=(
            "'incoming' = Telegram → Frontend; "
            "'outgoing' = Frontend → Telegram"
        ),
    )
    timestamp: str = Field(..., description="ISO-8601 UTC timestamp")
    sequence: int = Field(..., description="Monotonically increasing sequence number")
    username: Optional[str] = Field(
        default=None, description="Username of the owning participant"
    )
