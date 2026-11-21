"""Bots, strategy configs (immutable versions), lifecycle and the go-live gate (SPEC 8.1, 11)."""

import dataclasses
from datetime import UTC, datetime
from typing import Annotated
from uuid import UUID

import numpy as np
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.schemas_bots import (
    BotCreate,
    BotDetail,
    BotPatch,
    ConfigOut,
    GateCheckOut,
    GatesOut,
    GoLiveIn,
    LogEntryOut,
    PerformanceOut,
    RunnerStatus,
    SignalOut,
    StrategyPreset,
    TradeOut,
)
from app.api.services import Services, get_services
from app.auth.audit import audit
from app.auth.deps import CurrentUser, Db, TotpUser, client_ip, current_user
from app.backtest.registry import default_params, make_strategy, strategy_names
from app.bots.gates import GoLiveStatus, evaluate_go_live, snapshot_matches
from app.bots.paper import PaperComparison
from app.bots.paper import compare as compare_paper
from app.core.models import (
    AuditLog,
    Backtest,
    Bot,
    BotMode,
    BotStatus,
    ExchangeAccount,
    Market,
    Order,
    Position,
    RiskEvent,
    RiskProfile,
    Signal,
    StrategyConfig,
    Trade,
)
from app.runtime.runner import UNSUPPORTED

router = APIRouter(prefix="/api/v1", dependencies=[Depends(current_user)], tags=["bots"])
Svc = Annotated[Services, Depends(get_services)]

PRESETS = {
    "s1": ("Trend pullback", "ซื้อเมื่อราคาพักตัวในขาขึ้น (4H เทรนด์ขึ้น, 1H ย่อแล้วเด้ง)", None),
    "s2": ("Mean reversion", "ซื้อเมื่อราคาหลุดแถบล่างในตลาดไซด์เวย์ เป้าเส้นกลาง", None),
    "s3": ("Breakout", "ซื้อเมื่อทะลุกรอบหลัง squeeze พร้อมวอลุ่ม (สัญญาณน้อยมาก)", None),
    "s4": (
        "Grid",
        "วางคำสั่งเป็นชั้นในกรอบราคา",
        "R:R ต่อไม้ < 1 ผ่าน Risk Engine แบบออเดอร์เดี่ยวไม่ได้ — ยังใช้จริงไม่ได้",
    ),
}


def numeric_params(strategy: str) -> dict[str, float]:
    p = default_params(strategy)
    return {
        f.name: float(getattr(p, f.name))
        for f in dataclasses.fields(p)
        if isinstance(getattr(p, f.name), int | float) and not isinstance(getattr(p, f.name), bool)
    }


@router.get("/strategies", response_model=list[StrategyPreset])
async def strategies() -> list[StrategyPreset]:
    return [
        StrategyPreset(
            id=s,
            name=PRESETS[s][0],
            description=PRESETS[s][1],
            params=numeric_params(s),
            warning=PRESETS[s][2],
        )
        for s in strategy_names()
    ]


def validate_config(
    svc: Services, strategy: str, params: dict[str, float], symbols: list[str]
) -> None:
    unknown = [s for s in symbols if s not in svc.settings.symbols]
    if unknown:
        raise HTTPException(422, f"unsupported symbols: {unknown}")
    allowed = numeric_params(strategy)
    bad = sorted(set(params) - set(allowed))
    if bad:
        raise HTTPException(422, f"unknown parameters for {strategy}: {bad}")
    try:
        overrides = {
            k: type(default_params(strategy).__getattribute__(k))(v) for k, v in params.items()
        }
        make_strategy(strategy, overrides)
    except (ValueError, TypeError) as e:
        raise HTTPException(422, str(e)) from e


async def default_risk_profile_id(db: AsyncSession, svc: Services) -> UUID:
    row = (
        await db.execute(select(RiskProfile).where(RiskProfile.name == "default"))
    ).scalar_one_or_none()
    if row is None:
        p = svc.profile
        row = RiskProfile(
            name="default",
            risk_per_trade=p.risk_per_trade,
            max_positions=p.max_positions,
            max_symbol_exposure=p.max_symbol_exposure,
            max_total_exposure=p.max_total_exposure,
            max_open_risk=p.max_open_risk,
            max_bucket_risk=p.max_bucket_risk,
            min_cash_reserve=p.min_cash_reserve,
            daily_loss=p.daily_loss,
            weekly_loss=p.weekly_loss,
            max_dd=p.max_drawdown,
        )
        db.add(row)
        await db.flush()
    return row.id


async def active_config(db: AsyncSession, bot_id: UUID) -> StrategyConfig | None:
    return (
        (
            await db.execute(
                select(StrategyConfig)
                .where(StrategyConfig.bot_id == bot_id, StrategyConfig.is_active)
                .order_by(StrategyConfig.version.desc())
            )
        )
        .scalars()
        .first()
    )


def detail(bot: Bot, cfg: StrategyConfig | None) -> BotDetail:
    return BotDetail(
        id=bot.id,
        name=bot.name,
        account_id=bot.account_id,
        market=str(bot.market),
        symbols=list(bot.symbols),
        status=str(bot.status),
        mode=str(bot.mode),
        config=ConfigOut(strategy=cfg.strategy, params=cfg.params, version=cfg.version)
        if cfg
        else None,
        created_at=bot.created_at,
    )


async def get_bot(db: AsyncSession, bot_id: UUID) -> Bot:
    bot = await db.get(Bot, bot_id)
    if bot is None:
        raise HTTPException(404, "bot not found")
    return bot


@router.get("/bots", response_model=list[BotDetail])
async def list_bots(db: Db) -> list[BotDetail]:
    bots = (await db.execute(select(Bot).order_by(Bot.created_at.desc()))).scalars().all()
    return [detail(b, await active_config(db, b.id)) for b in bots]


@router.post("/bots", response_model=BotDetail, status_code=201)
async def create_bot(
    body: BotCreate, user: CurrentUser, request: Request, svc: Svc, db: Db
) -> BotDetail:
    if await db.get(ExchangeAccount, body.account_id) is None:
        raise HTTPException(422, "unknown account")
    validate_config(svc, body.strategy, body.params, body.symbols)
    bot = Bot(
        account_id=body.account_id,
        name=body.name,
        market=Market.SPOT,
        symbols=body.symbols,
        status=BotStatus.DRAFT,
        mode=BotMode.PAPER,
        risk_profile_id=await default_risk_profile_id(db, svc),
    )
    db.add(bot)
    await db.flush()
    cfg = StrategyConfig(
        bot_id=bot.id, strategy=body.strategy, params=body.params, version=1, is_active=True
    )
    db.add(cfg)
    audit(
        db,
        user.user_id,
        "bot.create",
        f"bot:{bot.id}",
        after={
            "name": body.name,
            "strategy": body.strategy,
            "symbols": body.symbols,
            "params": body.params,
        },
        ip=client_ip(request),
    )
    await db.commit()
    return detail(bot, cfg)


@router.get("/bots/{bot_id}", response_model=BotDetail)
async def read_bot(bot_id: UUID, db: Db) -> BotDetail:
    bot = await get_bot(db, bot_id)
    return detail(bot, await active_config(db, bot.id))


@router.patch("/bots/{bot_id}", response_model=BotDetail)
async def patch_bot(
    bot_id: UUID, body: BotPatch, user: CurrentUser, request: Request, svc: Svc, db: Db
) -> BotDetail:
    bot = await get_bot(db, bot_id)
    if bot.status in (BotStatus.RUNNING, BotStatus.PAPER):
        raise HTTPException(409, "pause the bot before changing its configuration")
    cfg = await active_config(db, bot.id)
    assert cfg is not None
    before = {
        "name": bot.name,
        "symbols": list(bot.symbols),
        "params": cfg.params,
        "version": cfg.version,
    }
    symbols = body.symbols if body.symbols is not None else list(bot.symbols)
    params = body.params if body.params is not None else cfg.params
    validate_config(svc, cfg.strategy, params, symbols)
    if body.name is not None:
        bot.name = body.name
    bot.symbols = symbols
    if params != cfg.params:  # versions are immutable: edit = new version, never update in place
        cfg.is_active = False
        await db.flush()
        cfg = StrategyConfig(
            bot_id=bot.id,
            strategy=cfg.strategy,
            params=params,
            version=cfg.version + 1,
            is_active=True,
        )
        db.add(cfg)
    audit(
        db,
        user.user_id,
        "bot.update",
        f"bot:{bot.id}",
        before=before,
        after={"name": bot.name, "symbols": symbols, "params": params, "version": cfg.version},
        ip=client_ip(request),
    )
    await db.commit()
    return detail(bot, cfg)


async def _transition(
    bot_id: UUID, action: str, user: CurrentUser, request: Request, svc: Services, db: AsyncSession
) -> BotDetail:
    bot = await get_bot(db, bot_id)
    old = bot.status
    if bot.status == BotStatus.KILLED:
        raise HTTPException(409, "bot is KILLED: reset the kill switch first")
    if action == "start":
        if svc.breakers is not None and svc.breakers.kill_switch_active:
            raise HTTPException(409, "kill switch is active")
        if bot.status not in (BotStatus.DRAFT, BotStatus.PAUSED):
            raise HTTPException(409, f"cannot start a bot in {bot.status}")
        cfg = await active_config(db, bot.id)
        if cfg is not None and cfg.strategy.lower() in UNSUPPORTED:
            raise HTTPException(409, "the grid strategy is not run live yet: it cannot be started")
        account = await db.get(ExchangeAccount, bot.account_id)
        if account is None or account.permissions_checked_at is None:
            raise HTTPException(409, "verify the account's API key first")
        bot.status = BotStatus.PAPER if bot.mode == BotMode.PAPER else BotStatus.RUNNING
    elif action == "pause":
        if bot.status not in (BotStatus.PAPER, BotStatus.RUNNING):
            raise HTTPException(409, f"cannot pause a bot in {bot.status}")
        bot.status = BotStatus.PAUSED
    else:  # stop
        bot.status = BotStatus.DRAFT
        bot.mode = BotMode.PAPER  # a stopped bot always goes back to paper: live must be re-earned
    audit(
        db,
        user.user_id,
        f"bot.{action}",
        f"bot:{bot.id}",
        before={"status": str(old)},
        after={"status": str(bot.status), "mode": str(bot.mode)},
        ip=client_ip(request),
    )
    await db.commit()
    return detail(bot, await active_config(db, bot.id))


@router.post("/bots/{bot_id}/start", response_model=BotDetail)
async def start_bot(
    bot_id: UUID, user: CurrentUser, request: Request, svc: Svc, db: Db
) -> BotDetail:
    return await _transition(bot_id, "start", user, request, svc, db)


@router.post("/bots/{bot_id}/pause", response_model=BotDetail)
async def pause_bot(
    bot_id: UUID, user: CurrentUser, request: Request, svc: Svc, db: Db
) -> BotDetail:
    return await _transition(bot_id, "pause", user, request, svc, db)


@router.post("/bots/{bot_id}/stop", response_model=BotDetail)
async def stop_bot(
    bot_id: UUID, user: CurrentUser, request: Request, svc: Svc, db: Db
) -> BotDetail:
    return await _transition(bot_id, "stop", user, request, svc, db)


# ---- go-live gate ----------------------------------------------------------------------------


GATE_CACHE_S = 300  # the comparison runs backtests: reuse it for a few minutes


async def paper_comparison(
    svc: Services, db: AsyncSession, bot: Bot, cfg: StrategyConfig, started: datetime | None
) -> PaperComparison | None:
    if started is None:
        return None
    key = f"paper_cmp:{bot.id}:{cfg.id}"
    now = datetime.now(UTC)
    hit = svc.extras.get(key)
    if hit is not None and (now - hit[0]).total_seconds() < GATE_CACHE_S:
        cached: PaperComparison = hit[1]
        return cached
    paper_r = float(
        (
            await db.execute(
                select(func.coalesce(func.sum(Trade.pnl_r), 0))
                .join(Position, Position.id == Trade.position_id)
                .where(Position.bot_id == bot.id, Position.opened_at >= started)
            )
        ).scalar_one()
    )
    result = await compare_paper(
        svc.candles,
        cfg.strategy.lower(),
        dict(cfg.params or {}),
        list(bot.symbols),
        started,
        now,
        paper_r,
    )
    svc.extras[key] = (now, result)
    return result


async def compute_gates(svc: Services, db: AsyncSession, bot: Bot) -> GoLiveStatus:
    cfg = await active_config(db, bot.id)
    assert cfg is not None
    gate1: bool | None = None
    failures: list[str] = []
    runs = (
        await db.execute(
            select(Backtest).where(Backtest.status == "DONE").order_by(Backtest.created_at.desc())
        )
    ).scalars()
    for run in runs:
        m = run.metrics or {}
        if m.get("walk_forward") and snapshot_matches(
            run.strategy_config_snapshot, cfg.strategy, cfg.params, list(bot.symbols)
        ):
            gate1 = bool(m["gate1"]["passed"])
            failures = list(m["gate1"]["failures"])
            break
    started = (
        await db.execute(
            select(func.min(AuditLog.ts)).where(
                AuditLog.action == "bot.start", AuditLog.target == f"bot:{bot.id}"
            )
        )
    ).scalar_one()

    async def count_events(kind: str) -> int:
        q = (
            select(func.count())
            .select_from(RiskEvent)
            .where(
                RiskEvent.bot_id == bot.id, RiskEvent.type == kind, RiskEvent.resolved_at.is_(None)
            )
        )
        return int((await db.execute(q)).scalar_one())

    comparison = await paper_comparison(svc, db, bot, cfg, started)
    return evaluate_go_live(
        gate1_passed=gate1,
        gate1_failures=failures,
        paper_started_at=started,
        now=datetime.now(UTC),
        paper_deviation=comparison.deviation if comparison else None,
        paper_detail=comparison.detail if comparison else None,
        unhandled_order_errors=await count_events("ORDER_ERROR"),
        recon_mismatches=await count_events("RECON_MISMATCH"),
        testnet_only=svc.settings.binance_testnet_only,
    )


@router.get("/bots/{bot_id}/gates", response_model=GatesOut)
async def gates(bot_id: UUID, svc: Svc, db: Db) -> GatesOut:
    st = await compute_gates(svc, db, await get_bot(db, bot_id))
    return GatesOut(
        allowed=st.allowed,
        checks=[GateCheckOut(name=c.name, ok=c.ok, detail=c.detail) for c in st.checks],
    )


@router.post("/bots/{bot_id}/go-live", response_model=BotDetail)
async def go_live(
    bot_id: UUID, body: GoLiveIn, user: TotpUser, request: Request, svc: Svc, db: Db
) -> BotDetail:
    bot = await get_bot(db, bot_id)
    if bot.status not in (BotStatus.PAPER, BotStatus.PAUSED) or bot.mode != BotMode.PAPER:
        raise HTTPException(409, "only a paper bot can go live")
    st = await compute_gates(svc, db, bot)
    if not st.allowed:
        failed = [f"{c.name}: {c.detail}" for c in st.checks if not c.ok]
        raise HTTPException(403, {"message": "go-live gate not passed", "failed": failed})
    bot.mode = BotMode.LIVE
    bot.status = BotStatus.RUNNING
    audit(
        db,
        user.user_id,
        "bot.go_live",
        f"bot:{bot.id}",
        after={"mode": "live"},
        ip=client_ip(request),
    )
    await db.commit()
    await svc.notifier.send(f"Bot {bot.name} switched to LIVE")
    return detail(bot, await active_config(db, bot.id))


# ---- read models -----------------------------------------------------------------------------


@router.get("/bots/{bot_id}/performance", response_model=PerformanceOut)
async def performance(bot_id: UUID, db: Db) -> PerformanceOut:
    await get_bot(db, bot_id)
    rows = (
        await db.execute(
            select(Trade.pnl_usdt, Trade.pnl_r, Position.closed_at)
            .join(Position, Position.id == Trade.position_id)
            .where(Position.bot_id == bot_id)
            .order_by(Position.closed_at)
        )
    ).all()
    if not rows:
        return PerformanceOut(
            n_trades=0,
            win_rate=0,
            profit_factor=None,
            expectancy_r=0,
            net_pnl=0,
            max_drawdown=0,
            sharpe=0,
            equity=[],
            drawdown=[],
        )
    pnl = np.array([float(r[0]) for r in rows])
    rs = np.array([float(r[1]) for r in rows])
    times = [int(r[2].timestamp()) if r[2] else 0 for r in rows]
    curve = np.cumsum(pnl)
    peak = np.maximum.accumulate(np.concatenate([[0.0], curve]))[1:]
    dd = np.where(peak > 0, (peak - curve) / np.where(peak > 0, peak, 1), 0.0)
    wins, losses = pnl[pnl > 0].sum(), -pnl[pnl < 0].sum()
    sharpe = (
        float(pnl.mean() / pnl.std(ddof=1) * np.sqrt(len(pnl)))
        if len(pnl) > 2 and pnl.std() > 0
        else 0.0
    )
    return PerformanceOut(
        n_trades=len(rows),
        win_rate=float((pnl > 0).mean()),
        profit_factor=float(wins / losses) if losses > 0 else None,
        expectancy_r=float(rs.mean()),
        net_pnl=sum((r[0] for r in rows), start=0),
        max_drawdown=float(dd.max()),
        sharpe=sharpe,
        equity=list(zip(times, curve.tolist(), strict=True)),
        drawdown=list(zip(times, dd.tolist(), strict=True)),
    )


CHECKLIST = [
    "kill_switch",
    "breakers",
    "stale_data",
    "stop_valid",
    "risk_reward",
    "exposure",
    "cash_reserve",
    "min_order",
]
REASON_TO_CHECK = {
    "KILL_SWITCH": "kill_switch",
    "BREAKER_ACTIVE": "breakers",
    "STALE_DATA": "stale_data",
    "CLOCK_DRIFT": "stale_data",
    "NO_STOP": "stop_valid",
    "BAD_STOP_SIDE": "stop_valid",
    "NO_TARGET": "risk_reward",
    "RR_TOO_LOW": "risk_reward",
    "MAX_POSITIONS": "exposure",
    "SYMBOL_EXPOSURE": "exposure",
    "TOTAL_EXPOSURE": "exposure",
    "OPEN_RISK": "exposure",
    "BUCKET_RISK": "exposure",
    "CASH_RESERVE": "cash_reserve",
    "INSUFFICIENT_FUNDS": "cash_reserve",
    "BELOW_MIN_QTY": "min_order",
    "BELOW_MIN_NOTIONAL": "min_order",
}


def signal_out(s: Signal) -> SignalOut:
    risk = float(s.entry - s.stop)
    rr = float(s.tp1 - s.entry) / risk if s.tp1 is not None and risk > 0 else None
    decision = str(s.decision)
    failed = REASON_TO_CHECK.get(s.reject_reason or "")
    if decision == "SKIPPED":
        checks = [
            GateCheckOut(
                name="score_threshold", ok=False, detail=s.reject_reason or "score below threshold"
            )
        ]
    else:
        checks = [
            GateCheckOut(
                name=c,
                ok=not (decision == "REJECTED" and c == failed),
                detail=(s.reject_reason or "")
                if decision == "REJECTED" and c == failed
                else "passed",
            )
            for c in CHECKLIST
        ]
    return SignalOut(
        id=s.id,
        ts=s.created_at,
        symbol=s.symbol,
        strategy=s.strategy,
        side=str(s.side),
        entry=s.entry,
        stop=s.stop,
        tp1=s.tp1,
        s_tech=s.s_tech,
        s_ml=s.s_ml,
        s_ai=s.s_ai,
        score=s.score,
        decision=decision,
        reject_reason=s.reject_reason,
        rr=rr,
        checks=checks,
    )


@router.get("/signals", response_model=list[SignalOut])
async def signals(
    db: Db,
    bot_id: UUID | None = None,
    decision: str | None = Query(None, pattern="^(TAKEN|SKIPPED|REJECTED)$"),
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
) -> list[SignalOut]:
    q = select(Signal).order_by(Signal.created_at.desc()).limit(limit)
    if bot_id:
        q = q.where(Signal.bot_id == bot_id)
    if decision:
        q = q.where(Signal.decision == decision)
    return [signal_out(s) for s in (await db.execute(q)).scalars()]


@router.get("/trades", response_model=list[TradeOut])
async def trades(
    db: Db, bot_id: UUID | None = None, limit: Annotated[int, Query(ge=1, le=500)] = 100
) -> list[TradeOut]:
    q = (
        select(Trade, Position)
        .join(Position, Position.id == Trade.position_id)
        .order_by(Position.closed_at.desc().nulls_last())
        .limit(limit)
    )
    if bot_id:
        q = q.where(Position.bot_id == bot_id)
    return [
        TradeOut(
            id=t.id,
            symbol=p.symbol,
            opened_at=p.opened_at,
            closed_at=p.closed_at,
            pnl_usdt=t.pnl_usdt,
            pnl_r=t.pnl_r,
            fees=t.fees,
            exit_reason=t.exit_reason,
        )
        for t, p in (await db.execute(q)).all()
    ]


# ---- activity log + runner status -------------------------------------------------------------

LEVELS = {"info": "info", "warning": "warning", "critical": "critical"}


@router.get("/bots/{bot_id}/logs", response_model=list[LogEntryOut])
async def bot_logs(
    bot_id: UUID, db: Db, limit: Annotated[int, Query(ge=1, le=500)] = 200
) -> list[LogEntryOut]:
    """Everything the bot did and why, newest first (SPEC 1.5: explainable)."""
    await get_bot(db, bot_id)
    out: list[LogEntryOut] = []
    for s in (
        await db.execute(
            select(Signal)
            .where(Signal.bot_id == bot_id)
            .order_by(Signal.created_at.desc())
            .limit(limit)
        )
    ).scalars():
        decision = str(s.decision)
        out.append(
            LogEntryOut(
                ts=s.created_at,
                kind="signal",
                level="info"
                if decision == "TAKEN"
                else "warning"
                if decision == "REJECTED"
                else "info",
                title=f"{decision} {s.strategy.upper()} {s.symbol}",
                detail=(
                    f"entry {s.entry:.2f} stop {s.stop:.2f} score {s.score:.0f}"
                    + (f" - {s.reject_reason}" if s.reject_reason else "")
                ),
            )
        )
    for o in (
        await db.execute(
            select(Order)
            .where(Order.bot_id == bot_id)
            .order_by(Order.created_at.desc())
            .limit(limit)
        )
    ).scalars():
        out.append(
            LogEntryOut(
                ts=o.created_at,
                kind="order",
                level="info",
                title=f"{o.leg} {o.side!s} {o.type} {o.status}",
                detail=f"{o.symbol} qty {o.qty:f}" + (f" @ {o.price:f}" if o.price else ""),
            )
        )
    for t, p in (
        await db.execute(
            select(Trade, Position)
            .join(Position, Position.id == Trade.position_id)
            .where(Position.bot_id == bot_id)
            .order_by(Trade.created_at.desc())
            .limit(limit)
        )
    ).all():
        out.append(
            LogEntryOut(
                ts=t.created_at,
                kind="trade",
                level="info" if t.pnl_usdt >= 0 else "warning",
                title=f"Closed {p.symbol}: {t.exit_reason}",
                detail=f"{t.pnl_usdt:+.2f} USDT ({t.pnl_r:+.2f}R), fees {t.fees:.2f}",
            )
        )
    for e in (
        await db.execute(
            select(RiskEvent)
            .where(RiskEvent.bot_id == bot_id)
            .order_by(RiskEvent.created_at.desc())
            .limit(limit)
        )
    ).scalars():
        out.append(
            LogEntryOut(
                ts=e.created_at,
                kind="risk",
                level=e.severity if e.severity in LEVELS else "warning",
                title=e.type,
                detail=", ".join(f"{k}={v}" for k, v in (e.payload or {}).items())[:300],
            )
        )
    for a in (
        await db.execute(
            select(AuditLog)
            .where(AuditLog.target == f"bot:{bot_id}")
            .order_by(AuditLog.ts.desc())
            .limit(limit)
        )
    ).scalars():
        out.append(
            LogEntryOut(
                ts=a.ts,
                kind="audit",
                level="info",
                title=a.action,
                detail=", ".join(f"{k}={v}" for k, v in (a.after or {}).items()),
            )
        )
    out.sort(key=lambda x: x.ts, reverse=True)
    return out[:limit]


@router.get("/runner/status", response_model=RunnerStatus)
async def runner_status(svc: Svc) -> RunnerStatus:
    """Is the bot runner alive? It refreshes a Redis key every 10 s (expires after 40 s)."""
    if svc.redis is None:
        return RunnerStatus(alive=False)
    try:
        raw = await svc.redis.get("runner:heartbeat")
    except Exception:
        return RunnerStatus(alive=False)
    if not raw:
        return RunnerStatus(alive=False)
    beat = datetime.fromisoformat(raw)
    age = (datetime.now(UTC) - beat).total_seconds()
    return RunnerStatus(alive=age <= 30, last_beat=beat, age_s=round(age, 1))
