from typing import Literal

from pydantic import Field, field_validator, model_validator

from app.components.accounts.schemas import StrictInput


class ProfilePatch(StrictInput):
    displayName: str | None = Field(default=None, max_length=100)
    university: str | None = Field(default=None, max_length=100)
    department: str | None = Field(default=None, max_length=100)
    uiLanguage: Literal["en", "ko"] | None = None
    summaryLanguage: Literal["auto", "en", "ko"] | None = None
    noteFormat: str | None = Field(default=None, min_length=1, max_length=36)

    @field_validator("displayName", "university", "department", mode="before")
    @classmethod
    def trim_text(cls, value):
        return value.strip() if isinstance(value, str) else value

    @model_validator(mode="after")
    def supplied_fields(self):
        if not self.model_fields_set or any(
            getattr(self, field) is None for field in self.model_fields_set
        ):
            raise ValueError("Supply a profile field; null values are not accepted.")
        return self


class FormatInput(StrictInput):
    name: str = Field(min_length=1, max_length=60)
    instructions: str = Field(min_length=1, max_length=300)

    @field_validator("name", "instructions", mode="before")
    @classmethod
    def trim_text(cls, value):
        return value.strip() if isinstance(value, str) else value


class CloseInput(StrictInput):
    password: str = Field(min_length=1, max_length=128)
    confirmation: Literal["CLOSE"]
