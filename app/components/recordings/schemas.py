import re
from datetime import UTC, datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.components.courses.schemas import CourseInput


class UploadInput(CourseInput):
    id: UUID
    courseId: UUID
    fileName: str = Field(min_length=1, max_length=255)
    sizeBytes: int = Field(gt=0, le=9007199254740991)
    sha256: str = Field(pattern=r"^[a-f0-9]{64}$")

    @field_validator("id", "courseId", mode="before")
    @classmethod
    def uuid_value(cls, value):
        return UUID(value) if isinstance(value, str) else value

    @field_validator("fileName")
    @classmethod
    def plain_name(cls, value):
        value = value.strip()
        if not value or value in {".", ".."} or re.search(r"[/\\\x00-\x1f\x7f]", value):
            raise ValueError("Use a plain file name")
        return value


class RecordingResponse(BaseModel):
    model_config = ConfigDict(frozen=True)
    id: UUID
    courseId: UUID
    courseTitle: str
    title: str
    sizeBytes: int
    durationSeconds: float | None
    contentType: str
    createdAt: datetime

    @field_validator("createdAt")
    @classmethod
    def utc_date(cls, value):
        return value.astimezone(UTC)


class UploadResponse(BaseModel):
    model_config = ConfigDict(frozen=True)
    id: UUID
    courseId: UUID
    courseTitle: str
    title: str
    fileName: str
    sizeBytes: int
    uploadedBytes: int
    sha256: str
    status: str
    errorCode: str
    chunkBytes: int = 4 * 1024 * 1024
    maxDurationSeconds: int | None
    recording: RecordingResponse | None
    createdAt: datetime

    @field_validator("createdAt")
    @classmethod
    def utc_date(cls, value):
        return value.astimezone(UTC)
