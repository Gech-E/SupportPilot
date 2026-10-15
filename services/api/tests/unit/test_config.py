from typing import Any

import pytest
from pydantic import SecretStr, ValidationError

from app.core.config import Settings

GOOD_SECRET = "a-properly-long-random-secret-value-0123456789"


def build(**overrides: Any) -> Settings:
    values: dict[str, Any] = {
        "_env_file": None,
        "database_url": SecretStr("postgresql+asyncpg://u:p@localhost/db"),
        "session_secret": SecretStr(GOOD_SECRET),
        "app_env": "local",
    }
    values.update(overrides)
    return Settings(**values)


def test_valid_local_settings_load() -> None:
    settings = build()
    assert settings.app_env == "local"
    assert not settings.is_hardened


def test_short_session_secret_is_rejected() -> None:
    with pytest.raises(ValidationError, match="at least 32"):
        build(session_secret=SecretStr("too-short"))


@pytest.mark.parametrize("environment", ["staging", "production"])
def test_placeholder_secret_is_rejected_when_hardened(environment: str) -> None:
    with pytest.raises(ValidationError, match="placeholder"):
        build(app_env=environment, session_secret=SecretStr("CHANGE_ME_" + "x" * 40))


@pytest.mark.parametrize("environment", ["staging", "production"])
def test_insecure_cookies_are_rejected_when_hardened(environment: str) -> None:
    with pytest.raises(ValidationError, match="COOKIE_SECURE"):
        build(app_env=environment, cookie_secure=False)


def test_insecure_cookies_are_allowed_locally() -> None:
    assert build(cookie_secure=False).cookie_secure is False


def test_wildcard_cors_origin_is_rejected() -> None:
    with pytest.raises(ValidationError, match="exact origins"):
        build(cors_origins=["*"])


def test_secrets_are_not_exposed_by_repr() -> None:
    rendered = repr(build())
    assert GOOD_SECRET not in rendered
    assert "u:p@localhost" not in rendered
