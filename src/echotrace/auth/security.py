"""Password hashing and JWT session tokens for EchoTrace's login system."""

import os
import time
from datetime import datetime, timedelta, timezone

import bcrypt
import jwt
from sqlalchemy import text
from sqlalchemy.engine import Connection

JWT_SECRET = os.environ.get("JWT_SECRET")
JWT_ALGORITHM = "HS256"
TOKEN_EXPIRY_HOURS = 24

# In-memory login-attempt limiter, keyed by "ip:username". Fine for a
# single backend instance (our Docker Compose deployment); if this is ever
# scaled to multiple replicas, move to a shared store (e.g. Redis) instead.
_failed_attempts: dict[str, list[float]] = {}
MAX_FAILED_ATTEMPTS = 5
LOCKOUT_WINDOW_SECONDS = 300


def check_rate_limit(key: str) -> None:
    """Raises AuthError if `key` has too many recent failed login attempts."""
    now = time.time()
    attempts = [t for t in _failed_attempts.get(key, []) if now - t < LOCKOUT_WINDOW_SECONDS]
    _failed_attempts[key] = attempts
    if len(attempts) >= MAX_FAILED_ATTEMPTS:
        raise AuthError("Too many failed login attempts. Try again in a few minutes.")


def record_failed_attempt(key: str) -> None:
    _failed_attempts.setdefault(key, []).append(time.time())


def clear_failed_attempts(key: str) -> None:
    _failed_attempts.pop(key, None)


class AuthError(Exception):
    pass


def _require_secret() -> str:
    if not JWT_SECRET:
        raise RuntimeError(
            "JWT_SECRET is not set. Add one to .env (see .env.example) — "
            "never run authentication with a missing or default secret."
        )
    return JWT_SECRET


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(password: str, password_hash: str) -> bool:
    return bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("utf-8"))


def create_access_token(username: str) -> str:
    payload = {
        "sub": username,
        "exp": datetime.now(timezone.utc) + timedelta(hours=TOKEN_EXPIRY_HOURS),
        "iat": datetime.now(timezone.utc),
    }
    return jwt.encode(payload, _require_secret(), algorithm=JWT_ALGORITHM)


def decode_access_token(token: str) -> str:
    """Returns the username encoded in the token. Raises AuthError if the
    token is missing, malformed, expired, or forged."""
    try:
        payload = jwt.decode(token, _require_secret(), algorithms=[JWT_ALGORITHM])
    except jwt.ExpiredSignatureError:
        raise AuthError("Session expired, please log in again.")
    except jwt.InvalidTokenError:
        raise AuthError("Invalid session token.")
    return payload["sub"]


def register_user(conn: Connection, username: str, password: str) -> None:
    username = username.strip()
    if not username or not password:
        raise AuthError("Username and password are required.")
    if len(password) < 8:
        raise AuthError("Password must be at least 8 characters.")

    existing = conn.execute(
        text("SELECT id FROM users WHERE username = :username"), {"username": username}
    ).fetchone()
    if existing:
        raise AuthError("That username is already taken.")

    conn.execute(
        text("INSERT INTO users (username, password_hash) VALUES (:username, :password_hash)"),
        {"username": username, "password_hash": hash_password(password)},
    )
    conn.commit()


def authenticate_user(conn: Connection, username: str, password: str) -> str:
    """Returns a JWT access token on success. Raises AuthError on failure."""
    row = conn.execute(
        text("SELECT password_hash FROM users WHERE username = :username"),
        {"username": username.strip()},
    ).fetchone()
    if row is None or not verify_password(password, row[0]):
        raise AuthError("Incorrect username or password.")
    return create_access_token(username.strip())


def get_user_id(conn: Connection, username: str) -> int | None:
    row = conn.execute(
        text("SELECT id FROM users WHERE username = :username"), {"username": username.strip()}
    ).fetchone()
    return row[0] if row else None
