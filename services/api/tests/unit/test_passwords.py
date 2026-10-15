from app.core.passwords import DUMMY_HASH, hash_password, verify_password


def test_correct_password_verifies() -> None:
    password_hash = hash_password("a long passphrase")
    assert verify_password(password_hash, "a long passphrase")


def test_wrong_password_does_not_verify() -> None:
    password_hash = hash_password("a long passphrase")
    assert not verify_password(password_hash, "another passphrase")


def test_hash_is_argon2id_and_salted() -> None:
    first = hash_password("same password")
    second = hash_password("same password")
    assert first.startswith("$argon2id$")
    assert first != second


def test_malformed_hash_returns_false_instead_of_raising() -> None:
    assert not verify_password("not-a-hash", "whatever")
    assert not verify_password("", "whatever")


def test_dummy_hash_is_valid_but_never_matches_real_input() -> None:
    assert DUMMY_HASH.startswith("$argon2id$")
    assert not verify_password(DUMMY_HASH, "any password an attacker tries")
