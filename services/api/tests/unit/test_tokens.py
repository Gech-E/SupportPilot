import uuid
from datetime import UTC, datetime, timedelta

import jwt
import pytest

from app.core.tokens import (
    InvalidTokenError,
    create_session_token,
    csrf_is_valid,
    csrf_token_for,
    decode_session_token,
)

SECRET = "unit-test-secret-" + "x" * 32
TTL = timedelta(minutes=30)


def test_session_token_round_trip() -> None:
    user_id = uuid.uuid4()
    token = create_session_token(user_id, secret=SECRET, ttl=TTL)
    assert decode_session_token(token, secret=SECRET) == user_id


def test_token_signed_with_another_secret_is_rejected() -> None:
    token = create_session_token(uuid.uuid4(), secret="a" * 40, ttl=TTL)
    with pytest.raises(InvalidTokenError):
        decode_session_token(token, secret="b" * 40)


def test_expired_token_is_rejected() -> None:
    issued = datetime.now(UTC) - timedelta(hours=2)
    token = create_session_token(uuid.uuid4(), secret=SECRET, ttl=TTL, now=issued)
    with pytest.raises(InvalidTokenError):
        decode_session_token(token, secret=SECRET)


def test_tampered_token_is_rejected() -> None:
    token = create_session_token(uuid.uuid4(), secret=SECRET, ttl=TTL)
    header, payload, signature = token.split(".")
    forged = ".".join([header, payload[:-2] + "AA", signature])
    with pytest.raises(InvalidTokenError):
        decode_session_token(forged, secret=SECRET)


def test_unsigned_token_with_alg_none_is_rejected() -> None:
    claims = {
        "sub": str(uuid.uuid4()),
        "iss": "supportpilot",
        "iat": datetime.now(UTC),
        "exp": datetime.now(UTC) + TTL,
    }
    unsigned = jwt.encode(claims, key=None, algorithm="none")
    with pytest.raises(InvalidTokenError):
        decode_session_token(unsigned, secret=SECRET)


def test_token_with_wrong_issuer_is_rejected() -> None:
    claims = {
        "sub": str(uuid.uuid4()),
        "iss": "someone-else",
        "iat": datetime.now(UTC),
        "exp": datetime.now(UTC) + TTL,
    }
    token = jwt.encode(claims, SECRET, algorithm="HS256")
    with pytest.raises(InvalidTokenError):
        decode_session_token(token, secret=SECRET)


def test_token_with_non_uuid_subject_is_rejected() -> None:
    claims = {
        "sub": "not-a-uuid",
        "iss": "supportpilot",
        "iat": datetime.now(UTC),
        "exp": datetime.now(UTC) + TTL,
    }
    token = jwt.encode(claims, SECRET, algorithm="HS256")
    with pytest.raises(InvalidTokenError):
        decode_session_token(token, secret=SECRET)


@pytest.mark.parametrize("garbage", ["", "abc", "a.b.c", "....."])
def test_malformed_tokens_are_rejected(garbage: str) -> None:
    with pytest.raises(InvalidTokenError):
        decode_session_token(garbage, secret=SECRET)


def test_csrf_token_is_bound_to_its_session() -> None:
    session_a = create_session_token(uuid.uuid4(), secret=SECRET, ttl=TTL)
    session_b = create_session_token(uuid.uuid4(), secret=SECRET, ttl=TTL)
    token_a = csrf_token_for(session_a, secret=SECRET)

    assert csrf_is_valid(session_a, token_a, secret=SECRET)
    assert not csrf_is_valid(session_b, token_a, secret=SECRET)


@pytest.mark.parametrize("supplied", [None, "", "wrong"])
def test_csrf_rejects_missing_or_wrong_values(supplied: str | None) -> None:
    session = create_session_token(uuid.uuid4(), secret=SECRET, ttl=TTL)
    assert not csrf_is_valid(session, supplied, secret=SECRET)


def test_csrf_token_depends_on_the_secret() -> None:
    session = create_session_token(uuid.uuid4(), secret=SECRET, ttl=TTL)
    assert csrf_token_for(session, secret="a" * 40) != csrf_token_for(session, secret="b" * 40)
