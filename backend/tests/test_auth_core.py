import uuid
from datetime import UTC, datetime, timedelta

import pyotp
import pytest

from app.auth.audit import scrub
from app.auth.core import (
    LoginLimiter,
    TokenError,
    TotpVerifier,
    hash_password,
    make_token,
    new_totp_secret,
    read_token,
    totp_uri,
    verify_password,
)
from app.auth.crypto import CryptoError, EnvelopeCipher, generate_master_key

SECRET = "s" * 40


def test_password_hash_is_argon2id_and_verifies() -> None:
    h = hash_password("correct horse")
    assert h.startswith("$argon2id$")
    assert verify_password(h, "correct horse")
    assert not verify_password(h, "wrong")
    assert not verify_password("not-a-hash", "x")


def test_totp_accepts_a_code_once_and_tolerates_30s_skew() -> None:
    secret = new_totp_secret()
    v = TotpVerifier()
    now = 1_700_000_000.0
    code = pyotp.TOTP(secret).at(now)
    assert v.verify("u", secret, code, now=now)
    assert not v.verify("u", secret, code, now=now)  # replay
    later = pyotp.TOTP(secret).at(now + 60)
    assert v.verify("u", secret, later, now=now + 60)
    assert not v.verify(
        "u", secret, pyotp.TOTP(secret).at(now), now=now + 60
    )  # older than last used
    assert not v.verify("u2", secret, "abcdef", now=now) and not v.verify(
        "u2", secret, "12345", now=now
    )
    skew = pyotp.TOTP(secret).at(now + 30)
    assert v.verify("u3", secret, skew, now=now)  # code of the next window, clock slightly behind
    assert totp_uri(secret, "a@b.c").startswith("otpauth://totp/")


def test_tokens_roundtrip_and_reject_wrong_type_expiry_and_tampering() -> None:
    uid = uuid.uuid4()
    tok = make_token(SECRET, uid, "a@b.c", "access")
    c = read_token(SECRET, tok, "access")
    assert c.user_id == uid and c.email == "a@b.c"
    with pytest.raises(TokenError):
        read_token(SECRET, tok, "refresh")
    with pytest.raises(TokenError):
        read_token("o" * 40, tok, "access")
    old = make_token(SECRET, uid, "a@b.c", "access", now=datetime.now(UTC) - timedelta(minutes=16))
    with pytest.raises(TokenError):
        read_token(SECRET, old, "access")
    with pytest.raises(TokenError):
        read_token(SECRET, "garbage", "access")


def test_login_limiter_blocks_after_five_failures_and_expires() -> None:
    lim = LoginLimiter()
    for i in range(4):
        lim.fail("k", now=100 + i)
    assert not lim.blocked("k", now=104)
    lim.fail("k", now=104)
    assert lim.blocked("k", now=105) and lim.retry_after("k", now=105) > 0
    assert not lim.blocked("other", now=105)
    assert not lim.blocked("k", now=100 + 15 * 60 + 5)  # window passed
    lim.fail("z", now=1)
    lim.clear("z")
    assert lim.retry_after("z", now=2) == 0


def test_envelope_encryption_roundtrip_binding_and_tamper_detection() -> None:
    c = EnvelopeCipher.from_b64(generate_master_key())
    blob = c.encrypt(b"api-secret", aad=b"account:1")
    assert b"api-secret" not in blob
    assert c.decrypt(blob, aad=b"account:1") == b"api-secret"
    assert c.encrypt(b"api-secret", aad=b"account:1") != blob  # fresh data key + nonce each time
    with pytest.raises(CryptoError):
        c.decrypt(blob, aad=b"account:2")  # bound to its record
    with pytest.raises(CryptoError):
        c.decrypt(blob[:-1] + bytes([blob[-1] ^ 1]), aad=b"account:1")
    with pytest.raises(CryptoError):
        EnvelopeCipher.from_b64(generate_master_key()).decrypt(blob, aad=b"account:1")
    with pytest.raises(CryptoError):
        c.decrypt(b"\x09" + blob[1:], aad=b"account:1")
    with pytest.raises(CryptoError, match="not configured"):
        EnvelopeCipher.from_b64("")
    with pytest.raises(CryptoError):
        EnvelopeCipher(b"short")
    with pytest.raises(CryptoError):
        EnvelopeCipher.from_b64("***not base64***")


def test_audit_scrub_masks_credentials() -> None:
    assert scrub({"label": "x", "api_secret": "s", "Password": "p", "totp": "1"}) == {
        "label": "x",
        "api_secret": "***",
        "Password": "***",
        "totp": "***",
    }
    assert scrub(None) is None


def test_production_wiring_provides_a_database_for_auth() -> None:
    """Regression: build_services once forgot db, so login answered 503 in the real app."""
    from app.core.config import Settings
    from app.main import build_services

    svc = build_services(
        Settings(_env_file=None, database_url="postgresql+asyncpg://u:p@127.0.0.1:1/x")
    )
    assert svc.db is not None and svc.trading is None
