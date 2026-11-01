from datetime import UTC, datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


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


class ScheduleInput(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    days: list[int] = Field(min_length=1, max_length=7)
    startTime: str = Field(pattern=r"^([01][0-9]|2[0-3]):[0-5][0-9]$")
    endTime: str = Field(pattern=r"^([01][0-9]|2[0-3]):[0-5][0-9]$")
    room: str = Field(default="", max_length=100)

    @model_validator(mode="after")
    def valid_slot(self):
        if len(set(self.days)) != len(self.days) or any(day < 0 or day > 6 for day in self.days):
            raise ValueError("Choose unique weekdays from 0 to 6.")
        if self.startTime >= self.endTime:
            raise ValueError("The end time must follow the start time.")
        self.room = self.room.strip()
        return self


class CourseCreate(CourseInput):
    professor: str = Field(default="", max_length=100)
    color: str = Field(default="#396c50", pattern=r"^#[0-9a-fA-F]{6}$")
    timetableId: UUID | None = Field(default=None, strict=False)
    schedules: list[ScheduleInput] = Field(default_factory=list, max_length=14)

    @field_validator("professor")
    @classmethod
    def trim_professor(cls, value):
        return value.strip()


class CoursePatch(CourseCreate):
    title: str | None = Field(default=None, min_length=1, max_length=100)

    @model_validator(mode="after")
    def supplied_fields(self):
        if not self.model_fields_set or ("title" in self.model_fields_set and self.title is None):
            raise ValueError("Supply a course field.")
        return self


class CourseDetailResponse(CourseResponse):
    professor: str
    color: str
    timetableId: UUID | None
    readOnly: bool
    schedules: list[ScheduleInput]
