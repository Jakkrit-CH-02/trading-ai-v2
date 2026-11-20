"""Passwords (argon2id), TOTP, JWTs and the login rate limiter."""

import time
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any, Literal

import jwt
import pyotp
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError

_ph = PasswordHasher()  # argon2id by default


def hash_password(password: str) -> str:
    return _ph.hash(password)


def verify_password(password_hash: str, password: str) -> bool:
    try:
        return _ph.verify(password_hash, password)
    except (VerificationError, InvalidHashError):
        return False


# ---- TOTP ---------------------------------------------------------------------------------


def new_totp_secret() -> str:
    return pyotp.random_base32()


def totp_uri(secret: str, email: str, issuer: str = "Softtrade") -> str:
    return pyotp.TOTP(secret).provisioning_uri(name=email, issuer_name=issuer)


@dataclass
class TotpVerifier:
    """Accepts a code once: a code (or an older one) seen for a user is never accepted again."""

    _last: dict[str, int] = field(default_factory=dict)

    def reset(self, user_id: str) -> None:
        """Forget the last accepted code (the secret was rotated, so old counters mean nothing)."""
        self._last.pop(user_id, None)

    def verify(self, user_id: str, secret: str, code: str, now: float | None = None) -> bool:
        if not (code.isdigit() and len(code) == 6):
            return False
        t = time.time() if now is None else now
        totp = pyotp.TOTP(secret)
        for step in (-1, 0, 1):  # +-30 s clock skew
            counter = int(t // 30) + step
            if counter <= self._last.get(user_id, -1):
                continue
            if totp.at(counter * 30) == code:
                self._last[user_id] = counter
                return True
        return False


# ---- JWT ----------------------------------------------------------------------------------

ACCESS_TTL = timedelta(minutes=15)
SESSION_TTL = timedelta(hours=12)
TokenType = Literal["access", "refresh"]


@dataclass(frozen=True)
class Claims:
    user_id: uuid.UUID
    email: str
    type: TokenType


class TokenError(Exception):
    pass


def make_token(
    secret: str, user_id: uuid.UUID, email: str, type_: TokenType, now: datetime | None = None
) -> str:
    n = now or datetime.now(UTC)
    ttl = ACCESS_TTL if type_ == "access" else SESSION_TTL
    payload: dict[str, Any] = {
        "sub": str(user_id),
        "email": email,
        "typ": type_,
        "iat": n,
        "exp": n + ttl,
    }
    return jwt.encode(payload, secret, algorithm="HS256")


def read_token(secret: str, token: str, expected: TokenType) -> Claims:
    try:
        p = jwt.decode(
            token, secret, algorithms=["HS256"], options={"require": ["exp", "sub", "typ"]}
        )
        if p["typ"] != expected:
            raise TokenError("wrong token type")
        return Claims(uuid.UUID(p["sub"]), p.get("email", ""), expected)
    except (jwt.PyJWTError, ValueError) as e:
        raise TokenError(str(e)) from e


# ---- login rate limit ------------------------------------------------------------------------


@dataclass
class LoginLimiter:
    """5 failed attempts per 15 minutes per key (ip + email). Success clears the key."""

    limit: int = 5
    window_s: float = 15 * 60
    _fails: dict[str, list[float]] = field(default_factory=dict)

    def _recent(self, key: str, now: float) -> list[float]:
        recent = [t for t in self._fails.get(key, []) if now - t < self.window_s]
        self._fails[key] = recent
        return recent

    def blocked(self, key: str, now: float | None = None) -> bool:
        return len(self._recent(key, time.time() if now is None else now)) >= self.limit

    def retry_after(self, key: str, now: float | None = None) -> int:
        t = time.time() if now is None else now
        recent = self._recent(key, t)
        return max(1, int(self.window_s - (t - recent[0]))) if recent else 0

    def fail(self, key: str, now: float | None = None) -> None:
        t = time.time() if now is None else now
        self._recent(key, t).append(t)

    def clear(self, key: str) -> None:
        self._fails.pop(key, None)
