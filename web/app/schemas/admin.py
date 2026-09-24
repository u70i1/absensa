"""Validation contracts for administrator login."""

from pydantic import BaseModel, Field, field_validator


class AdminLoginRequest(BaseModel):
    username: str = Field(min_length=1, max_length=100)
    password: str = Field(min_length=1, max_length=1024)

    @field_validator("username")
    @classmethod
    def normalize_username(cls, value: str) -> str:
        normalized = value.strip().casefold()
        if not normalized:
            raise ValueError("username must not be blank")
        return normalized
