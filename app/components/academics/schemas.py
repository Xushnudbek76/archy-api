from uuid import UUID

from pydantic import Field, field_validator

from app.components.accounts.schemas import StrictInput
from app.components.courses.schemas import CourseCreate


class NamedInput(StrictInput):
    name: str = Field(min_length=1, max_length=60)

    @field_validator("name", mode="before")
    @classmethod
    def trim_name(cls, value):
        return value.strip() if isinstance(value, str) else value


class TimetableInput(NamedInput):
    termId: UUID = Field(strict=False)


class ImportPreview(StrictInput):
    url: str = Field(min_length=1, max_length=300)


class ImportConfirm(StrictInput):
    requestId: UUID = Field(strict=False)
    timetableId: UUID = Field(strict=False)
    courses: list[CourseCreate] = Field(min_length=1, max_length=50)
