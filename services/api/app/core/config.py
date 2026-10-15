"""Application settings, validated at startup so a bad configuration fails fast.

All configuration comes from environment variables (see ``.env.example``). Nothing else in the
code base reads ``os.environ``.
"""

from functools import lru_cache
from typing import Any, Literal, Self

from pydantic import Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

_MIN_SECRET_LENGTH = 32
_PLACEHOLDER_MARKER = "CHANGE_ME"
_HARDENED_ENVIRONMENTS = frozenset({"staging", "production"})


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_env: Literal["local", "test", "staging", "production"] = "local"

    # Connection for the restricted ``supportpilot_app`` role. Migrations use a different URL.
    database_url: SecretStr
    # Signs session tokens and derives CSRF tokens.
    session_secret: SecretStr

    session_ttl_minutes: int = Field(default=60, ge=5, le=60 * 24 * 7)
    cookie_secure: bool = True
    cors_origins: list[str] = Field(default_factory=list)

    # Brute-force protection (per client IP and email, and per client IP overall).
    login_max_attempts: int = Field(default=5, ge=1)
    auth_ip_max_attempts: int = Field(default=20, ge=1)
    auth_window_seconds: int = Field(default=300, ge=1)

    @property
    def is_hardened(self) -> bool:
        return self.app_env in _HARDENED_ENVIRONMENTS

    @model_validator(mode="after")
    def _validate_security_settings(self) -> Self:
        secret = self.session_secret.get_secret_value()
        if len(secret) < _MIN_SECRET_LENGTH:
            raise ValueError(f"SESSION_SECRET must be at least {_MIN_SECRET_LENGTH} characters")
        if "*" in self.cors_origins:
            raise ValueError("CORS_ORIGINS must list exact origins; '*' is not allowed")
        if self.is_hardened:
            if _PLACEHOLDER_MARKER in secret:
                raise ValueError("SESSION_SECRET still has its placeholder value")
            if not self.cookie_secure:
                raise ValueError("COOKIE_SECURE must be true in staging and production")
        return self


@lru_cache
def get_settings() -> Settings:
    # Required fields come from the environment; the empty kwargs keep static type checkers
    # from demanding them as constructor arguments.
    no_overrides: dict[str, Any] = {}
    return Settings(**no_overrides)
