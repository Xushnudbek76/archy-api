from uuid import UUID

from pydantic import Field, field_validator

from app.components.accounts.schemas import StrictInput


class MessageInput(StrictInput):
    message: str = Field(min_length=1, max_length=2000)
    language: str = Field(pattern="^(en|ko)$")
    requestId: str

    @field_validator("message")
    @classmethod
    def trimmed(cls, value):
        if not value.strip():
            raise ValueError("Empty question")
        return value.strip()

    @field_validator("requestId")
    @classmethod
    def identifier(cls, value):
        return str(UUID(value))
