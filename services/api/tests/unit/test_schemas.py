import pytest
from pydantic import ValidationError

from app.schemas.auth import LoginRequest, SignupRequest
from app.schemas.workspace import WorkspaceCreate, WorkspaceUpdate


def test_signup_normalises_email_to_lowercase() -> None:
    request = SignupRequest(email="  Alice@Example.COM ", password="a long passphrase")
    assert request.email == "alice@example.com"


def test_signup_requires_at_least_twelve_characters() -> None:
    with pytest.raises(ValidationError):
        SignupRequest(email="alice@example.com", password="elevenchars")


def test_signup_caps_password_length() -> None:
    with pytest.raises(ValidationError):
        SignupRequest(email="alice@example.com", password="x" * 129)


def test_password_is_not_exposed_by_repr() -> None:
    request = SignupRequest(email="alice@example.com", password="a long passphrase")
    assert "a long passphrase" not in repr(request)
    assert "a long passphrase" not in request.model_dump_json()


def test_unknown_fields_are_rejected() -> None:
    with pytest.raises(ValidationError):
        LoginRequest.model_validate(
            {"email": "alice@example.com", "password": "x", "is_admin": True}
        )


def test_workspace_name_is_trimmed_and_bounded() -> None:
    assert WorkspaceCreate(name="  Acme  ").name == "Acme"
    with pytest.raises(ValidationError):
        WorkspaceCreate(name="   ")
    with pytest.raises(ValidationError):
        WorkspaceCreate(name="x" * 81)


def test_origins_are_normalised_and_deduplicated() -> None:
    update = WorkspaceUpdate(
        allowed_origins=[
            "HTTPS://Shop.Example.com",
            "https://shop.example.com",
            "http://localhost:3000",
        ]
    )
    assert update.allowed_origins == ["https://shop.example.com", "http://localhost:3000"]


@pytest.mark.parametrize(
    "origin",
    [
        "*",
        "example.com",
        "https://example.com/",
        "https://example.com/path",
        "https://example.com?x=1",
        "ftp://example.com",
        "https://",
        "javascript:alert(1)",
    ],
)
def test_invalid_origins_are_rejected(origin: str) -> None:
    with pytest.raises(ValidationError):
        WorkspaceUpdate(allowed_origins=[origin])


def test_too_many_origins_are_rejected() -> None:
    with pytest.raises(ValidationError):
        WorkspaceUpdate(allowed_origins=[f"https://site{i}.example.com" for i in range(21)])


@pytest.mark.parametrize("value", [-0.1, 1.1])
def test_confidence_threshold_must_be_a_probability(value: float) -> None:
    with pytest.raises(ValidationError):
        WorkspaceUpdate(confidence_threshold=value)


def test_budget_must_be_positive() -> None:
    with pytest.raises(ValidationError):
        WorkspaceUpdate(daily_token_budget=0)


def test_explicit_null_is_rejected_but_omission_is_fine() -> None:
    with pytest.raises(ValidationError):
        WorkspaceUpdate.model_validate({"name": None})
    assert WorkspaceUpdate.model_validate({}).model_dump(exclude_unset=True) == {}
