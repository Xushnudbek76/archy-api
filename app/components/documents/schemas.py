from uuid import UUID

from pydantic import BaseModel, Field, model_validator

from app.components.accounts.schemas import StrictInput
from app.components.courses.schemas import CourseInput, CourseResponse


class DocumentInput(CourseInput):
    courseId: UUID | None = Field(default=None, strict=False)
    recordingId: UUID | None = Field(default=None, strict=False)


class DocumentResponse(CourseResponse):
    isPinned: bool = False
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


class DocumentPatch(DocumentInput):
    title: str | None = Field(default=None, min_length=1, max_length=100)

    @model_validator(mode="after")
    def nonempty_patch(self):
        if not self.model_fields_set or ("title" in self.model_fields_set and self.title is None):
            raise ValueError("Supply a document field.")
        return self


class PinInput(StrictInput):
    pinned: bool
