from uuid import UUID

from pydantic import BaseModel, Field

from app.components.courses.schemas import CourseInput, CourseResponse


class DocumentInput(CourseInput):
    courseId: UUID | None = Field(default=None, strict=False)
    recordingId: UUID | None = Field(default=None, strict=False)


class DocumentResponse(CourseResponse):
    courseId: UUID | None
    recordingId: UUID | None
    hasPdf: bool
    fileName: str | None
    pdfSizeBytes: int | None
    pageCount: int | None


class DocumentDetail(DocumentResponse):
    text: str | None


class DocumentPage(BaseModel):
    items: list[DocumentResponse]
    total: int
    page: int
    pageSize: int
    nextPage: int | None
    previousPage: int | None
