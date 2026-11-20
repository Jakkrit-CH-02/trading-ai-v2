"""Login / refresh / TOTP gate against a real database (needs TEST_DATABASE_URL).

Async httpx client on the test's own loop: starlette's TestClient would run the app on another
loop, which asyncpg connections created here cannot be used from."""

import time
from collections.abc import AsyncIterator
from typing import Any

import httpx
import pyotp
import pytest
from pydantic import SecretStr
from sqlalchemy import func, select, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncEngine

from app.api.services import Services
from app.auth.crypto import generate_master_key
from app.auth.routes import create_user
from app.core.config import Settings
from app.core.db import make_session_factory
from app.core.models import AuditLog
from app.main import create_app
from app.marketdata.store import InMemoryCandleStore
from tests.conftest import needs_pg
from tests.test_api import FakeMarket

pytestmark = needs_pg
PASSWORD = "correct horse battery"
Env = tuple[httpx.AsyncClient, Services, str]


@pytest.fixture
async def env(pg_engine: AsyncEngine) -> AsyncIterator[Env]:
    svc = Services(
        settings=Settings(
            jwt_secret=SecretStr("j" * 40), master_key=SecretStr(generate_master_key())
        ),
        candles=InMemoryCandleStore(),
        market=FakeMarket(),
        db=make_session_factory(pg_engine),
    )
    _, secret = await create_user(svc, "Teng@Example.com", PASSWORD)
    transport = httpx.ASGITransport(app=create_app(svc))
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        yield c, svc, secret


def code(secret: str, offset: int = 0) -> str:
    return pyotp.TOTP(secret).at(time.time() + offset)


async def login(
    c: httpx.AsyncClient, secret: str, pw: str = PASSWORD, totp: str | None = None
) -> httpx.Response:
    body = {"email": "teng@example.com", "password": pw, "totp": totp or code(secret)}
    return await c.post("/api/v1/auth/login", json=body)


async def audit_actions(svc: Services) -> list[str]:
    assert svc.db
    async with svc.db() as s:
        return list((await s.execute(select(AuditLog.action).order_by(AuditLog.id))).scalars())


async def test_login_issues_access_token_and_httponly_refresh_cookie(env: Env) -> None:
    c, svc, secret = env
    r = await login(c, secret)
    assert r.status_code == 200
    j = r.json()
    assert j["email"] == "teng@example.com" and j["expires_in"] == 900
    cookie = r.headers["set-cookie"].lower()
    assert "httponly" in cookie and "samesite=strict" in cookie and "path=/api/v1/auth" in cookie
    me = await c.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {j['access_token']}"})
    assert me.json()["email"] == "teng@example.com"
    assert "auth.login" in await audit_actions(svc)


async def test_wrong_password_or_totp_gives_the_same_generic_401(env: Env) -> None:
    c, _, secret = env
    a = await login(c, secret, pw="nope")
    b = await login(c, secret, totp="000000")
    body = {"email": "x@y.z", "password": PASSWORD, "totp": code(secret)}
    unknown = await c.post("/api/v1/auth/login", json=body)
    assert a.status_code == b.status_code == unknown.status_code == 401
    assert a.json() == b.json() == unknown.json() == {"detail": "invalid credentials"}


async def test_totp_code_cannot_be_replayed(env: Env) -> None:
    c, _, secret = env
    one = code(secret)
    assert (await login(c, secret, totp=one)).status_code == 200
    assert (await login(c, secret, totp=one)).status_code == 401


async def test_five_failures_lock_out_even_the_correct_credentials(env: Env) -> None:
    c, svc, secret = env
    for _ in range(5):
        assert (await login(c, secret, pw="bad")).status_code == 401
    r = await login(c, secret)
    assert r.status_code == 429 and int(r.headers["retry-after"]) > 0
    assert (await audit_actions(svc)).count("auth.login_failed") == 5


async def test_refresh_uses_the_cookie_and_logout_clears_it(env: Env) -> None:
    c, _, secret = env
    assert (await c.post("/api/v1/auth/refresh")).status_code == 401  # no session yet
    await login(c, secret)
    r = await c.post("/api/v1/auth/refresh")
    assert r.status_code == 200 and r.json()["access_token"]
    assert (await c.post("/api/v1/auth/logout")).status_code == 204
    c.cookies.clear()
    assert (await c.post("/api/v1/auth/refresh")).status_code == 401


async def test_an_access_token_is_not_accepted_as_a_refresh_cookie(env: Env) -> None:
    c, _, secret = env
    access = (await login(c, secret)).json()["access_token"]
    c.cookies.clear()
    c.cookies.set("refresh_token", access, path="/api/v1/auth")
    assert (await c.post("/api/v1/auth/refresh")).status_code == 401


async def test_totp_setup_needs_a_current_code_and_rotates_the_secret(env: Env) -> None:
    c, svc, secret = env
    token = (await login(c, secret)).json()["access_token"]
    h: dict[str, Any] = {"Authorization": f"Bearer {token}"}
    url = "/api/v1/auth/totp/setup"
    assert (await c.post(url, headers=h)).status_code == 401  # no X-TOTP
    assert (await c.post(url, headers={**h, "X-TOTP": "123456"})).status_code == 401
    r = await c.post(url, headers={**h, "X-TOTP": code(secret, 30)})
    assert r.status_code == 200
    new = r.json()["secret"]
    assert new != secret and r.json()["uri"].startswith("otpauth://")
    assert (await login(c, secret, totp=code(secret, 30))).status_code == 401  # old secret is dead
    assert (await login(c, new, totp=code(new, 30))).status_code == 200
    assert "auth.totp_rotated" in await audit_actions(svc)


async def test_audit_log_is_append_only(env: Env) -> None:
    _, svc, _ = env
    assert svc.db
    async with svc.db() as s:
        assert (await s.execute(select(func.count()).select_from(AuditLog))).scalar_one() >= 1
        with pytest.raises(DBAPIError):
            await s.execute(text("UPDATE audit_log SET action = 'x'"))
        await s.rollback()
        with pytest.raises(DBAPIError):
            await s.execute(text("DELETE FROM audit_log"))
