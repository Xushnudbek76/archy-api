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


class QuizInput(NotesInput):
    questionType: Literal["multiple_choice", "true_false", "mixed"]
    questionCount: Literal[5, 10, 15]


class QuestionContent(StrictInput):
    type: Literal["multiple_choice", "true_false"]
    prompt: str = Field(min_length=1, max_length=800)
    options: list[str] = Field(min_length=2, max_length=4)
    correctAnswer: int = Field(ge=0, le=3)
    explanation: str = Field(min_length=1, max_length=1500)
    sourceIds: list[str] = Field(min_length=1, max_length=20)


class QuizContent(StrictInput):
    questions: list[QuestionContent] = Field(min_length=1, max_length=15)
