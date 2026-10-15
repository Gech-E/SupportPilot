import uuid

from pydantic import BaseModel, ConfigDict, EmailStr, Field, SecretStr, field_validator


class _EmailPayload(BaseModel):
    # Unknown fields are rejected so typos and mass-assignment attempts fail loudly.
    model_config = ConfigDict(extra="forbid")

    email: EmailStr

    @field_validator("email")
    @classmethod
    def _normalise_email(cls, value: str) -> str:
        return value.strip().lower()


class SignupRequest(_EmailPayload):
    # Length matters more than composition rules (NIST SP 800-63B). The upper bound limits the
    # CPU an attacker can force the hasher to spend.
    password: SecretStr = Field(min_length=12, max_length=128)


class LoginRequest(_EmailPayload):
    password: SecretStr = Field(min_length=1, max_length=128)


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    email: str
