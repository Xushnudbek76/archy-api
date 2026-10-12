from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator, model_validator

from app.libs.security import validate_password


class StrictInput(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class EmailRequest(StrictInput):
    email: EmailStr = Field(max_length=254)

    @field_validator("email", mode="before")
    @classmethod
    def normalize_email(cls, value):
        return value.strip().lower() if isinstance(value, str) else value


class LoginRequest(EmailRequest):
    password: str = Field(min_length=1, max_length=128)


class PasswordRequest(StrictInput):
    password: str = Field(min_length=10, max_length=128)
    passwordConfirmation: str = Field(min_length=10, max_length=128)

    @model_validator(mode="after")
    def matching_passwords(self):
        if self.password != self.passwordConfirmation:
            raise ValueError("Passwords must match")
        validate_password(self.password, str(getattr(self, "email", "")))
        return self


class SignupRequest(EmailRequest, PasswordRequest):
    displayName: str = Field(default="", max_length=100)

    @field_validator("displayName")
    @classmethod
    def trim_name(cls, value):
        return value.strip()


class ConfirmationRequest(StrictInput):
    token: str = Field(min_length=1, max_length=2048)


class ResetRequest(PasswordRequest):
    uid: str = Field(min_length=1, max_length=100)
    token: str = Field(min_length=1, max_length=200)
