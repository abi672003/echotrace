import os
import sys
from pathlib import Path

os.environ.setdefault("JWT_SECRET", "test-secret-not-for-production-use-only-32b")
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import pytest

from echotrace.auth.security import (
    AuthError,
    authenticate_user,
    create_access_token,
    decode_access_token,
    hash_password,
    register_user,
    verify_password,
)
from echotrace.db import get_connection, reset_engine_for_tests


@pytest.fixture
def conn(tmp_path):
    reset_engine_for_tests(f"sqlite:///{(tmp_path / 'test.sqlite').as_posix()}")
    c = get_connection()
    yield c
    c.close()


def test_password_is_hashed_not_stored_plaintext():
    hashed = hash_password("correct horse battery staple")
    assert hashed != "correct horse battery staple"
    assert verify_password("correct horse battery staple", hashed)
    assert not verify_password("wrong password", hashed)


def test_token_roundtrip():
    token = create_access_token("alice")
    assert decode_access_token(token) == "alice"


def test_forged_token_rejected():
    token = create_access_token("alice")
    # Flip a character in the *middle* of the signature segment, not the
    # last one: base64's final character can carry unused "don't care"
    # padding bits (since a 32-byte HMAC-SHA256 signature isn't a multiple
    # of 3 bytes), so tampering the last char is occasionally a no-op —
    # this was flaky. A middle character always spans a full encoded byte.
    header, payload, signature = token.split(".")
    mid = len(signature) // 2
    flipped = "A" if signature[mid] != "A" else "B"
    tampered = f"{header}.{payload}.{signature[:mid]}{flipped}{signature[mid + 1:]}"
    with pytest.raises(AuthError):
        decode_access_token(tampered)


def test_register_then_login(conn):
    register_user(conn, "bob", "hunter22plus")
    token = authenticate_user(conn, "bob", "hunter22plus")
    assert decode_access_token(token) == "bob"


def test_login_wrong_password_rejected(conn):
    register_user(conn, "carol", "correcthorsebattery")
    with pytest.raises(AuthError):
        authenticate_user(conn, "carol", "wrongpassword")


def test_login_unknown_user_rejected(conn):
    with pytest.raises(AuthError):
        authenticate_user(conn, "nobody", "whatever123")


def test_duplicate_username_rejected(conn):
    register_user(conn, "dave", "firstpassword")
    with pytest.raises(AuthError):
        register_user(conn, "dave", "secondpassword")


def test_short_password_rejected(conn):
    with pytest.raises(AuthError):
        register_user(conn, "eve", "short")
