from datetime import UTC, datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator


class CourseInput(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    title: str = Field(min_length=1, max_length=100)

    @field_validator("title", mode="before")
    @classmethod
    def trim_title(cls, value):
        return value.strip() if isinstance(value, str) else value


class CourseResponse(BaseModel):
    model_config = ConfigDict(frozen=True)
    id: UUID
    title: str
    archivedAt: datetime | None
    createdAt: datetime
    updatedAt: datetime

    @field_validator("archivedAt", "createdAt", "updatedAt")
    @classmethod
    def utc_dates(cls, value):
        return value.astimezone(UTC) if value else value
