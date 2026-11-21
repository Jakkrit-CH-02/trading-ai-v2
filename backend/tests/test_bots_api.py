"""Bots, risk profile, kill switch, accounts and the go-live gate against a real database."""

import uuid
from collections.abc import AsyncIterator
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any

import httpx
import pytest
from pydantic import SecretStr
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncEngine

from app.api.services import Services
from app.auth.core import TotpVerifier, make_token
from app.auth.crypto import generate_master_key
from app.auth.routes import create_user
from app.bots.gates import evaluate_go_live, snapshot_matches
from app.core.config import Settings
from app.core.db import make_session_factory
from app.core.models import (
    AuditLog,
    Backtest,
    ExchangeAccount,
    Position,
    PositionStatus,
    Side,
    Signal,
    Trade,
)
from app.main import create_app, restore_kill_state
from app.marketdata.store import InMemoryCandleStore
from app.notify.telegram import NullNotifier
from tests.conftest import needs_pg
from tests.test_api import FakeMarket

pytestmark = needs_pg
CODE = {"X-TOTP": "424242"}


class StubTotp(TotpVerifier):
    """Real TOTP is covered in test_auth_api; here any request with 424242 counts as verified."""

    def verify(self, user_id: str, secret: str, code: str, now: float | None = None) -> bool:
        return code == "424242"


class FakeProbe:
    def __init__(self, info: dict[str, Any]) -> None:
        self.info = info
        self.closed = False

    async def account_info(self) -> dict[str, Any]:
        return self.info

    async def aclose(self) -> None:
        self.closed = True


@dataclass
class Env:
    c: httpx.AsyncClient
    svc: Services
    info: dict[str, Any]
    notifier: NullNotifier
    user_id: uuid.UUID


@pytest.fixture
async def env(pg_engine: AsyncEngine) -> AsyncIterator[Env]:
    notifier = NullNotifier()
    info: dict[str, Any] = {"canTrade": True, "canWithdraw": False}
    svc = Services(
        settings=Settings(
            _env_file=None,
            jwt_secret=SecretStr("j" * 40),
            master_key=SecretStr(generate_master_key()),
            symbols=["BTCUSDT", "ETHUSDT"],
        ),
        candles=InMemoryCandleStore(),
        market=FakeMarket(),
        db=make_session_factory(pg_engine),
        notifier=notifier,
        totp=StubTotp(),
        adapter_factory=lambda key, secret, testnet: FakeProbe(info),
    )
    user, _ = await create_user(svc, "t@example.com", "pw-pw-pw-pw-pw")
    token = make_token("j" * 40, user.id, user.email, "access")
    transport = httpx.ASGITransport(app=create_app(svc))
    async with httpx.AsyncClient(
        transport=transport, base_url="http://test", headers={"Authorization": f"Bearer {token}"}
    ) as c:
        yield Env(c, svc, info, notifier, user.id)


async def add_account(e: Env, label: str = "demo") -> dict[str, Any]:
    r = await e.c.post(
        "/api/v1/accounts",
        json={"label": label, "api_key": "KEY-abcdef1234", "api_secret": "SECRET-xyz98765"},
        headers=CODE,
    )
    assert r.status_code == 201, r.text
    j: dict[str, Any] = r.json()
    return j


async def make_bot(e: Env, account_id: str, **over: Any) -> dict[str, Any]:
    body = {
        "name": "alpha",
        "account_id": account_id,
        "symbols": ["BTCUSDT"],
        "strategy": "s1",
        "params": {},
    }
    r = await e.c.post("/api/v1/bots", json={**body, **over})
    assert r.status_code == 201, r.text
    j: dict[str, Any] = r.json()
    return j


async def actions(e: Env) -> list[str]:
    assert e.svc.db
    async with e.svc.db() as s:
        return list((await s.execute(select(AuditLog.action).order_by(AuditLog.id))).scalars())


# ---- accounts ----


async def test_account_needs_totp_is_encrypted_at_rest_and_only_shows_last4(env: Env) -> None:
    body = {"label": "demo", "api_key": "KEY-abcdef1234", "api_secret": "SECRET-xyz98765"}
    assert (await env.c.post("/api/v1/accounts", json=body)).status_code == 401  # no X-TOTP
    acc = await add_account(env)
    assert acc["api_key_last4"] == "1234" and acc["permissions_checked_at"]
    assert "KEY-abcdef" not in str(acc) and "SECRET" not in str(acc)
    assert env.svc.db
    async with env.svc.db() as s:
        row = (await s.execute(select(ExchangeAccount))).scalar_one()
        assert b"KEY-abcdef1234" not in row.api_key_enc and b"SECRET" not in row.api_secret_enc
        audit_rows = (await s.execute(select(AuditLog.after))).scalars().all()
    assert "SECRET" not in str(audit_rows) and "KEY-abcdef" not in str(audit_rows)
    listed = (await env.c.get("/api/v1/accounts")).json()
    assert [a["api_key_last4"] for a in listed] == ["1234"]
    assert any("API key added" in m for m in env.notifier.sent)


async def test_a_key_that_cannot_trade_is_rejected_and_never_stored(env: Env) -> None:
    env.info["canTrade"] = False
    r = await env.c.post(
        "/api/v1/accounts",
        json={"label": "ro", "api_key": "KEY-abcdef1234", "api_secret": "SECRET-xyz98765"},
        headers=CODE,
    )
    assert r.status_code == 422 and "cannot trade" in str(r.json()["detail"]["problems"])
    assert (await env.c.get("/api/v1/accounts")).json() == []
    assert "account.rejected" in await actions(env)


async def test_a_demo_key_may_have_withdraw_rights_because_binance_cannot_turn_them_off(
    env: Env,
) -> None:
    """Play money only: for real accounts assess_permissions still rejects (test_notify)."""
    env.info["canWithdraw"] = True
    r = await env.c.post(
        "/api/v1/accounts",
        json={"label": "demo", "api_key": "KEY-abcdef1234", "api_secret": "SECRET-xyz98765"},
        headers=CODE,
    )
    assert r.status_code == 201


async def test_live_accounts_are_refused_before_gate_b(env: Env) -> None:
    r = await env.c.post(
        "/api/v1/accounts",
        json={
            "label": "live",
            "api_key": "KEY-abcdef1234",
            "api_secret": "SECRET-xyz98765",
            "is_testnet": False,
        },
        headers=CODE,
    )
    assert r.status_code == 403


async def test_verify_revokes_a_key_that_lost_trading_rights(env: Env) -> None:
    acc = await add_account(env)
    assert (await env.c.post(f"/api/v1/accounts/{acc['id']}/verify")).status_code == 200
    env.info["canTrade"] = False
    assert (await env.c.post(f"/api/v1/accounts/{acc['id']}/verify")).status_code == 422
    assert (await env.c.get("/api/v1/accounts")).json()[0]["permissions_checked_at"] is None
    assert (await env.c.post(f"/api/v1/accounts/{uuid.uuid4()}/verify")).status_code == 404


# ---- bots ----


async def test_strategy_presets_expose_defaults_and_the_grid_warning(env: Env) -> None:
    ps = {p["id"]: p for p in (await env.c.get("/api/v1/strategies")).json()}
    assert set(ps) == {"s1", "s2", "s3", "s4"}
    assert ps["s1"]["params"]["tp1_r"] == 2.0 and ps["s1"]["warning"] is None
    assert ps["s4"]["warning"]


async def test_create_validates_symbols_params_and_account(env: Env) -> None:
    acc = await add_account(env)
    url = "/api/v1/bots"
    ok = {
        "name": "a",
        "account_id": acc["id"],
        "symbols": ["BTCUSDT"],
        "strategy": "s1",
        "params": {},
    }
    assert (await env.c.post(url, json={**ok, "symbols": ["DOGEUSDT"]})).status_code == 422
    assert (await env.c.post(url, json={**ok, "params": {"nope": 1}})).status_code == 422
    assert (await env.c.post(url, json={**ok, "params": {"tp1_r": -5}})).status_code in (201, 422)
    assert (await env.c.post(url, json={**ok, "account_id": str(uuid.uuid4())})).status_code == 422
    assert (await env.c.post(url, json={**ok, "strategy": "s9"})).status_code == 422
    assert (await env.c.post(url, json={**ok, "name": ""})).status_code == 422


async def test_editing_params_creates_a_new_immutable_version(env: Env) -> None:
    acc = await add_account(env)
    bot = await make_bot(env, acc["id"])
    assert bot["status"] == "DRAFT" and bot["mode"] == "paper" and bot["config"]["version"] == 1
    r = await env.c.patch(f"/api/v1/bots/{bot['id']}", json={"params": {"tp1_r": 2.5}})
    assert r.status_code == 200 and r.json()["config"] == {
        "strategy": "s1",
        "params": {"tp1_r": 2.5},
        "version": 2,
    }
    assert env.svc.db
    async with env.svc.db() as s:
        rows = (
            await s.execute(
                text("SELECT version, is_active, params FROM strategy_configs ORDER BY version")
            )
        ).all()
    assert [(r[0], r[1]) for r in rows] == [(1, False), (2, True)]
    assert rows[0][2] == {}  # version 1 untouched
    renamed = await env.c.patch(f"/api/v1/bots/{bot['id']}", json={"name": "beta"})
    assert renamed.json()["config"]["version"] == 2  # a rename is not a new strategy version
    assert (
        await env.c.patch(f"/api/v1/bots/{uuid.uuid4()}", json={"name": "x"})
    ).status_code == 404


async def test_start_needs_a_verified_account_then_runs_paper_and_audits(env: Env) -> None:
    acc = await add_account(env)
    bot = await make_bot(env, acc["id"])
    env.info["canTrade"] = False
    await env.c.post(f"/api/v1/accounts/{acc['id']}/verify")  # un-verifies the account
    assert (await env.c.post(f"/api/v1/bots/{bot['id']}/start")).status_code == 409
    env.info["canTrade"] = True
    await env.c.post(f"/api/v1/accounts/{acc['id']}/verify")
    r = await env.c.post(f"/api/v1/bots/{bot['id']}/start")
    assert r.status_code == 200 and r.json()["status"] == "PAPER"
    assert (
        await env.c.post(f"/api/v1/bots/{bot['id']}/start")
    ).status_code == 409  # already running
    cfg = await env.c.patch(f"/api/v1/bots/{bot['id']}", json={"name": "z"})
    assert cfg.status_code == 409  # pause before editing
    assert (await env.c.post(f"/api/v1/bots/{bot['id']}/pause")).json()["status"] == "PAUSED"
    assert (await env.c.post(f"/api/v1/bots/{bot['id']}/pause")).status_code == 409
    assert (await env.c.post(f"/api/v1/bots/{bot['id']}/stop")).json()["status"] == "DRAFT"
    assert [a for a in await actions(env) if a.startswith("bot.")] == [
        "bot.create",
        "bot.start",
        "bot.pause",
        "bot.stop",
    ]
    listed = (await env.c.get("/api/v1/bots")).json()
    assert [b["name"] for b in listed] == ["alpha"]
    summary = (await env.c.get("/api/v1/bots/summary")).json()
    assert summary["bots"][0]["strategy"] == "S1" and summary["running"] == 0


# ---- kill switch + risk profile ----


async def test_kill_stops_every_bot_latches_and_only_a_totp_reset_releases_it(env: Env) -> None:
    acc = await add_account(env)
    bot = await make_bot(env, acc["id"])
    await env.c.post(f"/api/v1/bots/{bot['id']}/start")
    r = await env.c.post("/api/v1/risk/kill", json={"reason": "test"})  # no TOTP needed to stop
    assert r.status_code == 200 and r.json()["severity"] == "critical"
    assert (await env.c.get(f"/api/v1/bots/{bot['id']}")).json()["status"] == "KILLED"
    st = (await env.c.get("/api/v1/risk/status")).json()
    assert st["kill_switch"] is True and st["entries_blocked"] is True
    assert (await env.c.post(f"/api/v1/bots/{bot['id']}/start")).status_code == 409
    assert (await env.c.post("/api/v1/risk/kill/reset")).status_code == 401  # needs TOTP
    assert (await env.c.post("/api/v1/risk/kill/reset", headers=CODE)).status_code == 204
    assert (await env.c.get(f"/api/v1/bots/{bot['id']}")).json()[
        "status"
    ] == "PAUSED"  # not auto-resumed
    assert (await env.c.get("/api/v1/risk/status")).json()["kill_switch"] is False
    events = (await env.c.get("/api/v1/risk/events")).json()
    assert events[0]["type"] == "KILL_SWITCH" and events[0]["resolved_at"]
    assert {"risk.kill", "risk.kill_reset"} <= set(await actions(env))
    assert any("KILL SWITCH" in m for m in env.notifier.sent)


async def test_kill_state_is_restored_after_a_restart(env: Env) -> None:
    acc = await add_account(env)
    bot = await make_bot(env, acc["id"])
    await env.c.post(f"/api/v1/bots/{bot['id']}/start")
    await env.c.post("/api/v1/risk/kill", json={})
    env.svc.breakers = None  # simulate a fresh process
    await restore_kill_state(env.svc)
    assert env.svc.breakers is not None and env.svc.breakers.kill_switch_active


async def test_risk_profile_change_needs_totp_validates_bounds_and_is_audited(env: Env) -> None:
    cur = (await env.c.get("/api/v1/risk/profile")).json()
    assert Decimal(cur["risk_per_trade"]) == Decimal("0.005")
    assert (await env.c.put("/api/v1/risk/profile", json=cur)).status_code == 401
    too_risky = {**cur, "risk_per_trade": "0.05"}
    r = await env.c.put("/api/v1/risk/profile", json=too_risky, headers=CODE)
    assert r.status_code == 422 and "risk_per_trade" in r.text
    assert (await env.c.get("/api/v1/risk/profile")).json()["risk_per_trade"] == cur[
        "risk_per_trade"
    ]
    ok = {**cur, "risk_per_trade": "0.004", "max_positions": 3}
    r = await env.c.put("/api/v1/risk/profile", json=ok, headers=CODE)
    assert r.status_code == 200 and Decimal(r.json()["risk_per_trade"]) == Decimal("0.004")
    assert env.svc.profile.max_positions == 3
    assert "risk.profile_update" in await actions(env)
    assert "Risk profile changed" in env.notifier.sent


# ---- go-live gate ----


async def test_go_live_is_refused_with_the_failing_checks_and_needs_totp(env: Env) -> None:
    acc = await add_account(env)
    bot = await make_bot(env, acc["id"])
    await env.c.post(f"/api/v1/bots/{bot['id']}/start")
    g = (await env.c.get(f"/api/v1/bots/{bot['id']}/gates")).json()
    assert g["allowed"] is False
    failing = {c["name"] for c in g["checks"] if not c["ok"]}
    assert {
        "gate1_backtest",
        "gate2_paper_duration",
        "gate2_deviation",
        "gate_b_live_enabled",
    } <= failing
    assert (
        await env.c.post(f"/api/v1/bots/{bot['id']}/go-live", json={"confirm": True})
    ).status_code == 401
    r = await env.c.post(f"/api/v1/bots/{bot['id']}/go-live", json={"confirm": True}, headers=CODE)
    assert r.status_code == 403 and r.json()["detail"]["failed"]
    assert (await env.c.get(f"/api/v1/bots/{bot['id']}")).json()["mode"] == "paper"
    r = await env.c.post(f"/api/v1/bots/{bot['id']}/go-live", json={"confirm": False}, headers=CODE)
    assert r.status_code == 422


async def test_gate1_uses_only_a_backtest_of_the_exact_same_config(env: Env) -> None:
    acc = await add_account(env)
    bot = await make_bot(env, acc["id"])
    assert env.svc.db
    async with env.svc.db() as s:
        s.add(
            Backtest(
                strategy_config_snapshot={"strategy": "s1", "params": {}, "symbols": ["BTCUSDT"]},
                range={},
                fees_model={},
                status="DONE",
                metrics={
                    "walk_forward": True,
                    "gate1": {"passed": False, "failures": ["profit factor 0.67 < 1.3"]},
                },
            )
        )
        s.add(
            Backtest(  # a passing run for a different symbol set must not count
                strategy_config_snapshot={"strategy": "s1", "params": {}, "symbols": ["ETHUSDT"]},
                range={},
                fees_model={},
                status="DONE",
                metrics={"walk_forward": True, "gate1": {"passed": True, "failures": []}},
            )
        )
        await s.commit()
    g = (await env.c.get(f"/api/v1/bots/{bot['id']}/gates")).json()
    c1 = next(c for c in g["checks"] if c["name"] == "gate1_backtest")
    assert c1["ok"] is False and "profit factor 0.67" in c1["detail"]


def test_go_live_logic_all_green_only_when_every_gate_is_met() -> None:
    now = datetime(2026, 11, 20, tzinfo=UTC)
    base: dict[str, Any] = dict(
        gate1_passed=True,
        gate1_failures=[],
        paper_started_at=now - timedelta(days=30),
        now=now,
        paper_deviation=0.1,
        unhandled_order_errors=0,
        recon_mismatches=0,
        testnet_only=False,
    )
    assert evaluate_go_live(**base).allowed
    for over in (
        {"gate1_passed": None},
        {"gate1_passed": False, "gate1_failures": ["x"]},
        {"paper_started_at": None},
        {"paper_started_at": now - timedelta(days=27)},
        {"paper_deviation": None},
        {"paper_deviation": 0.31},
        {"unhandled_order_errors": 1},
        {"recon_mismatches": 2},
        {"testnet_only": True},
    ):
        assert not evaluate_go_live(**{**base, **over}).allowed, over
    assert snapshot_matches(
        {"strategy": "s1", "params": {}, "symbols": ["B", "A"]}, "s1", {}, ["A", "B"]
    )
    assert not snapshot_matches(
        {"strategy": "s1", "params": {"x": 1}, "symbols": ["A"]}, "s1", {}, ["A"]
    )


# ---- read models ----


async def test_performance_trades_and_signals_read_models(env: Env) -> None:
    acc = await add_account(env)
    bot = await make_bot(env, acc["id"])
    assert (await env.c.get(f"/api/v1/bots/{bot['id']}/performance")).json()["n_trades"] == 0
    bot_id = uuid.UUID(bot["id"])
    t0 = datetime(2026, 11, 1, tzinfo=UTC)
    assert env.svc.db
    async with env.svc.db() as s:
        for i, (pnl, r) in enumerate([(100, 1.0), (-50, -1.0), (80, 0.8)]):
            pos = Position(
                bot_id=bot_id,
                symbol="BTCUSDT",
                side=Side.BUY,
                qty=Decimal(1),
                avg_entry=Decimal(100),
                status=PositionStatus.CLOSED,
                opened_at=t0 + timedelta(days=i),
                closed_at=t0 + timedelta(days=i, hours=5),
            )
            s.add(pos)
            await s.flush()
            s.add(
                Trade(
                    position_id=pos.id,
                    pnl_usdt=Decimal(pnl),
                    pnl_r=Decimal(str(r)),
                    fees=Decimal(1),
                    slippage=Decimal(0),
                    holding_minutes=300,
                    exit_reason="tp1",
                )
            )
        s.add(
            Signal(
                bot_id=bot_id,
                symbol="BTCUSDT",
                strategy="s1",
                side=Side.BUY,
                entry=Decimal(100),
                stop=Decimal(98),
                tp1=Decimal(104),
                s_tech=Decimal(80),
                score=Decimal(70),
                decision="TAKEN",
            )
        )
        s.add(
            Signal(
                bot_id=bot_id,
                symbol="BTCUSDT",
                strategy="s1",
                side=Side.BUY,
                entry=Decimal(100),
                stop=Decimal(98),
                tp1=Decimal(101),
                decision="REJECTED",
                reject_reason="RR_TOO_LOW",
            )
        )
        s.add(
            Signal(
                bot_id=bot_id,
                symbol="BTCUSDT",
                strategy="s1",
                side=Side.BUY,
                entry=Decimal(100),
                stop=Decimal(98),
                decision="SKIPPED",
                reject_reason="SCORE_SKIP",
            )
        )
        await s.commit()
    p = (await env.c.get(f"/api/v1/bots/{bot['id']}/performance")).json()
    assert p["n_trades"] == 3 and p["win_rate"] == pytest.approx(2 / 3)
    assert p["profit_factor"] == pytest.approx(180 / 50) and Decimal(p["net_pnl"]) == 130
    assert p["expectancy_r"] == pytest.approx(0.2666, abs=1e-3)
    assert [e[1] for e in p["equity"]] == [100, 50, 130]
    assert p["max_drawdown"] == pytest.approx(0.5)  # 100 -> 50
    tr = (await env.c.get(f"/api/v1/trades?bot_id={bot['id']}")).json()
    assert len(tr) == 3 and tr[0]["symbol"] == "BTCUSDT"
    sg = (await env.c.get(f"/api/v1/signals?bot_id={bot['id']}")).json()
    by = {s["decision"]: s for s in sg}
    assert by["TAKEN"]["rr"] == pytest.approx(2.0) and all(c["ok"] for c in by["TAKEN"]["checks"])
    bad = [c for c in by["REJECTED"]["checks"] if not c["ok"]]
    assert [c["name"] for c in bad] == ["risk_reward"] and bad[0]["detail"] == "RR_TOO_LOW"
    assert by["SKIPPED"]["checks"][0]["name"] == "score_threshold"
    assert len((await env.c.get("/api/v1/signals?decision=REJECTED")).json()) == 1
    assert (await env.c.get("/api/v1/signals?decision=bogus")).status_code == 422
    assert (await env.c.get(f"/api/v1/bots/{uuid.uuid4()}/performance")).status_code == 404
    assert (await env.c.get(f"/api/v1/bots/{bot['id']}")).status_code == 200


# ---- runtime-facing endpoints ----


async def test_the_grid_strategy_cannot_be_started_yet(env: Env) -> None:
    acc = await add_account(env)
    bot = await make_bot(env, acc["id"], strategy="s4")
    r = await env.c.post(f"/api/v1/bots/{bot['id']}/start")
    assert r.status_code == 409 and "grid" in r.json()["detail"]


async def test_bot_logs_merge_every_source_newest_first(env: Env) -> None:
    from decimal import Decimal

    from app.core.models import (
        Decision,
        Order,
        OrderLeg,
        Position,
        PositionStatus,
        RiskEvent,
        Side,
        Trade,
    )
    from app.core.models import Signal as SignalRow

    acc = await add_account(env)
    bot = await make_bot(env, acc["id"])
    bid = uuid.UUID(bot["id"])
    assert (await env.c.post(f"/api/v1/bots/{bot['id']}/start")).status_code == 200
    assert env.svc.db
    async with env.svc.db.begin() as s:
        s.add(
            SignalRow(
                bot_id=bid,
                symbol="BTCUSDT",
                strategy="s1",
                side=Side.BUY,
                entry=Decimal(100),
                stop=Decimal(95),
                score=Decimal(72),
                decision=Decision.REJECTED,
                reject_reason="RR_TOO_LOW",
            )
        )
        s.add(
            RiskEvent(
                bot_id=bid, type="DATA_GAP", severity="warning", payload={"symbol": "BTCUSDT"}
            )
        )
        s.add(
            Order(
                bot_id=bid,
                client_order_id="c1",
                symbol="BTCUSDT",
                side=Side.BUY,
                type="LIMIT",
                price=Decimal(100),
                qty=Decimal(1),
                status="FILLED",
                leg=OrderLeg.ENTRY,
            )
        )
        pos = Position(
            bot_id=bid,
            symbol="BTCUSDT",
            side=Side.BUY,
            qty=Decimal(1),
            avg_entry=Decimal(100),
            status=PositionStatus.CLOSED,
            opened_at=datetime.now(UTC),
        )
        s.add(pos)
        await s.flush()
        s.add(
            Trade(
                position_id=pos.id,
                pnl_usdt=Decimal(-5),
                pnl_r=Decimal(-1),
                fees=Decimal(1),
                slippage=Decimal(0),
                holding_minutes=60,
                exit_reason="stop",
            )
        )
    logs = (await env.c.get(f"/api/v1/bots/{bot['id']}/logs")).json()
    assert {e["kind"] for e in logs} == {"signal", "risk", "order", "trade", "audit"}
    assert [e["ts"] for e in logs] == sorted((e["ts"] for e in logs), reverse=True)
    sig = next(e for e in logs if e["kind"] == "signal")
    assert sig["level"] == "warning" and "RR_TOO_LOW" in sig["detail"]
    assert next(e for e in logs if e["kind"] == "trade")["title"] == "Closed BTCUSDT: stop"
    assert next(e for e in logs if e["kind"] == "audit")["title"] == "bot.start"
    assert len((await env.c.get(f"/api/v1/bots/{bot['id']}/logs?limit=2")).json()) == 2
    assert (await env.c.get(f"/api/v1/bots/{uuid.uuid4()}/logs")).status_code == 404


class FakeRedis:
    def __init__(self, value: str | None, evaluated: dict[str, str] | None = None) -> None:
        self.value = value
        self.evaluated = evaluated or {}

    async def hgetall(self, key: str) -> dict[str, str]:
        assert key == "runner:last_eval"
        return self.evaluated

    async def get(self, key: str) -> str | None:
        assert key == "runner:heartbeat"
        return self.value


async def test_runner_status_reads_the_heartbeat(env: Env) -> None:
    assert (await env.c.get("/api/v1/runner/status")).json() == {
        "alive": False,
        "last_beat": None,
        "age_s": None,
        "evaluated": [],
    }  # no redis configured
    env.svc.redis = FakeRedis(None)
    assert (await env.c.get("/api/v1/runner/status")).json()["alive"] is False
    env.svc.redis = FakeRedis(datetime.now(UTC).isoformat())
    j = (await env.c.get("/api/v1/runner/status")).json()
    assert j["alive"] is True and j["age_s"] < 5
    note = '{"bar": "2026-11-21T12:00:00+00:00", "at": "2026-11-21T13:00:03+00:00"}'
    env.svc.redis = FakeRedis(datetime.now(UTC).isoformat(), {"BTCUSDT:1h": note, "junk": "x"})
    assert (await env.c.get("/api/v1/runner/status")).json()["evaluated"] == []  # bad note ignored
    env.svc.redis = FakeRedis(datetime.now(UTC).isoformat(), {"BTCUSDT:1h": note})
    ev = (await env.c.get("/api/v1/runner/status")).json()["evaluated"]
    assert ev == [
        {
            "symbol": "BTCUSDT",
            "interval": "1h",
            "bar_time": "2026-11-21T12:00:00Z",
            "processed_at": "2026-11-21T13:00:03Z",
        }
    ]
    env.svc.redis = FakeRedis((datetime.now(UTC) - timedelta(minutes=5)).isoformat())
    assert (await env.c.get("/api/v1/runner/status")).json()["alive"] is False  # stale beat
