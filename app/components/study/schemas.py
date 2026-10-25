from typing import Literal

from pydantic import Field

from app.components.accounts.schemas import StrictInput


class NotesInput(StrictInput):
    language: Literal["en", "ko"]


class Section(StrictInput):
    title: str = Field(min_length=1, max_length=200)
    text: str = Field(min_length=1, max_length=3000)
    sourceIds: list[str] = Field(min_length=1, max_length=20)


class NotesContent(StrictInput):
    overview: str = Field(min_length=1, max_length=12000)
    sections: list[Section] = Field(min_length=1, max_length=48)
