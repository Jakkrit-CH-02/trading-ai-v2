import httpx
import pytest

from app.api.accounts import assess_permissions
from app.notify.telegram import NullNotifier, TelegramNotifier, make_notifier

TOKEN = "123456:SECRET-BOT-TOKEN"


async def test_telegram_posts_the_message_to_the_configured_chat() -> None:
    seen: list[httpx.Request] = []

    def handler(req: httpx.Request) -> httpx.Response:
        seen.append(req)
        return httpx.Response(200, json={"ok": True})

    n = TelegramNotifier(TOKEN, "42", httpx.AsyncClient(transport=httpx.MockTransport(handler)))
    await n.send("hello")
    assert seen[0].url.path == f"/bot{TOKEN}/sendMessage"
    assert b'"chat_id":"42"' in seen[0].content.replace(b" ", b"") and b"hello" in seen[0].content
    assert TOKEN not in repr(n)


async def test_a_failing_alert_is_swallowed_and_never_leaks_the_token(
    capsys: pytest.CaptureFixture[str],
) -> None:
    def handler(req: httpx.Request) -> httpx.Response:
        return httpx.Response(500)

    n = TelegramNotifier(TOKEN, "42", httpx.AsyncClient(transport=httpx.MockTransport(handler)))
    await n.send("x")  # must not raise: an alert failure cannot break a kill switch
    out = capsys.readouterr()
    assert TOKEN not in out.out + out.err


def test_notifier_is_null_without_configuration() -> None:
    assert isinstance(make_notifier("", ""), NullNotifier)
    assert isinstance(make_notifier(TOKEN, "42"), TelegramNotifier)
    assert isinstance(make_notifier(TOKEN, ""), NullNotifier)


def test_permission_assessment() -> None:
    assert assess_permissions({"canTrade": True, "canWithdraw": False}) == []
    assert len(assess_permissions({"canTrade": True, "canWithdraw": True})) == 1
    assert len(assess_permissions({"canTrade": False})) == 1
    assert len(assess_permissions({"canTrade": False, "canWithdraw": True})) == 2


def test_notification_settings_never_expose_credentials() -> None:
    from fastapi.testclient import TestClient

    from app.core.config import Settings
    from app.main import create_app
    from tests.test_api import authed, make_services

    svc = make_services()
    svc.settings = Settings(
        _env_file=None,
        jwt_secret=svc.settings.jwt_secret,
        telegram_bot_token=TOKEN,
        telegram_chat_id="42",
    )
    from app.notify.telegram import NullNotifier as Null

    svc.notifier = Null()
    c: TestClient = authed(create_app(svc))
    j = c.get("/api/v1/settings/notifications").json()
    assert j == {"telegram_configured": False, "live_trading_enabled": False, "trading_env": "demo"}
    assert c.post("/api/v1/settings/notifications/test").status_code == 204
    assert svc.notifier.sent == ["Softtrade test alert"]
    assert TOKEN not in str(j)
