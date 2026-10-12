from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class Segment(StrictModel):
    start: float = Field(ge=0, allow_inf_nan=False)
    end: float = Field(gt=0, allow_inf_nan=False)
    text: str = Field(min_length=1, max_length=16000)

    @model_validator(mode="after")
    def ordered(self):
        if self.end <= self.start:
            raise ValueError("Invalid segment")
        return self


class Transcription(StrictModel):
    text: str = Field(min_length=1, max_length=200000)
    language: Literal["ko", "en"]
    segments: list[Segment] = Field(min_length=1, max_length=10000)


class LectureNote(StrictModel):
    overview: str = Field(min_length=1, max_length=1200)
    key_concepts: list[str] = Field(max_length=12)
    examples: list[str] = Field(max_length=8)
    review_questions: list[str] = Field(max_length=8)
    unclear_passages: list[str] = Field(max_length=8)

    @model_validator(mode="after")
    def bounded_text(self):
        if any(
            len(value) > 1200
            for items in (
                self.key_concepts,
                self.examples,
                self.review_questions,
                self.unclear_passages,
            )
            for value in items
        ):
            raise ValueError("Note text is too large")
        return self
