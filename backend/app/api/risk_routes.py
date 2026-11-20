"""Risk profile, kill switch and risk events (SPEC 3, 8.1)."""

from dataclasses import replace
from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select, update

from app.api.schemas_bots import KillIn, RiskEventOut, RiskProfileOut
from app.api.services import Services, get_services
from app.auth.audit import audit
from app.auth.deps import CurrentUser, Db, TotpUser, client_ip, current_user
from app.core.models import Bot, BotStatus, RiskEvent
from app.core.models import RiskProfile as RiskProfileRow
from app.risk import CircuitBreakers, RiskProfile
from app.risk.profile import RiskConfigError

router = APIRouter(prefix="/api/v1/risk", dependencies=[Depends(current_user)], tags=["risk"])
Svc = Annotated[Services, Depends(get_services)]

# the fields the UI may change; the rest of RiskProfile keeps its SPEC default
EDITABLE = (
    "risk_per_trade",
    "max_positions",
    "max_symbol_exposure",
    "max_total_exposure",
    "max_open_risk",
    "max_bucket_risk",
    "min_cash_reserve",
    "daily_loss",
    "weekly_loss",
    "max_drawdown",
)


def profile_out(p: RiskProfile) -> RiskProfileOut:
    return RiskProfileOut(**{k: getattr(p, k) for k in EDITABLE})


@router.get("/profile", response_model=RiskProfileOut)
async def read_profile(svc: Svc) -> RiskProfileOut:
    return profile_out(svc.profile)


@router.put("/profile", response_model=RiskProfileOut)
async def update_profile(
    body: RiskProfileOut, user: TotpUser, request: Request, svc: Svc, db: Db
) -> RiskProfileOut:
    """Always needs a TOTP code: loosening limits is a money-affecting change (SPEC 8)."""
    try:
        new = replace(svc.profile, **body.model_dump())
    except RiskConfigError as e:
        raise HTTPException(422, str(e)) from e
    before = profile_out(svc.profile).model_dump(mode="json")
    row = (
        await db.execute(select(RiskProfileRow).where(RiskProfileRow.name == "default"))
    ).scalar_one_or_none()
    if row is not None:
        row.risk_per_trade = new.risk_per_trade
        row.max_positions = new.max_positions
        row.max_symbol_exposure = new.max_symbol_exposure
        row.max_total_exposure = new.max_total_exposure
        row.max_open_risk = new.max_open_risk
        row.max_bucket_risk = new.max_bucket_risk
        row.min_cash_reserve = new.min_cash_reserve
        row.daily_loss = new.daily_loss
        row.weekly_loss = new.weekly_loss
        row.max_dd = new.max_drawdown
    audit(
        db,
        user.user_id,
        "risk.profile_update",
        "risk_profile:default",
        before=before,
        after=body.model_dump(mode="json"),
        ip=client_ip(request),
    )
    await db.commit()
    svc.profile = new
    if svc.breakers is not None:  # rebuild with the new limits but never drop a latched kill switch
        was_killed = svc.breakers.kill_switch_active
        svc.breakers = CircuitBreakers(new)
        if was_killed:
            svc.breakers.trigger_kill(datetime.now(UTC), "kept across profile change")
    await svc.notifier.send("Risk profile changed")
    return profile_out(new)


@router.get("/events", response_model=list[RiskEventOut])
async def events(db: Db, limit: int = 100) -> list[RiskEventOut]:
    rows = (
        await db.execute(
            select(RiskEvent).order_by(RiskEvent.created_at.desc()).limit(min(limit, 500))
        )
    ).scalars()
    return [
        RiskEventOut(
            id=e.id,
            ts=e.created_at,
            type=e.type,
            severity=e.severity,
            payload=e.payload,
            resolved_at=e.resolved_at,
        )
        for e in rows
    ]


@router.post("/kill", response_model=RiskEventOut)
async def kill(body: KillIn, user: CurrentUser, request: Request, svc: Svc, db: Db) -> RiskEventOut:
    """No second factor: stopping must always be one click. Resetting needs TOTP."""
    now = datetime.now(UTC)
    svc.risk_breakers().trigger_kill(now, body.reason)
    await db.execute(
        update(Bot).where(Bot.status != BotStatus.DRAFT).values(status=BotStatus.KILLED)
    )
    ev = RiskEvent(
        type="KILL_SWITCH",
        severity="critical",
        payload={"reason": body.reason, "by": str(user.user_id)},
    )
    db.add(ev)
    audit(
        db,
        user.user_id,
        "risk.kill",
        "kill_switch",
        after={"reason": body.reason},
        ip=client_ip(request),
    )
    await db.commit()
    await svc.notifier.send(f"KILL SWITCH triggered: {body.reason}")
    return RiskEventOut(
        id=ev.id,
        ts=ev.created_at,
        type=ev.type,
        severity=ev.severity,
        payload=ev.payload,
        resolved_at=None,
    )


@router.post("/kill/reset", status_code=204)
async def kill_reset(user: TotpUser, request: Request, svc: Svc, db: Db) -> None:
    svc.risk_breakers().reset_kill(totp_verified=True)  # TotpUser already verified the code
    await db.execute(
        update(Bot).where(Bot.status == BotStatus.KILLED).values(status=BotStatus.PAUSED)
    )
    await db.execute(
        update(RiskEvent)
        .where(RiskEvent.type == "KILL_SWITCH", RiskEvent.resolved_at.is_(None))
        .values(resolved_at=datetime.now(UTC), resolved_by=str(user.user_id))
    )
    audit(db, user.user_id, "risk.kill_reset", "kill_switch", ip=client_ip(request))
    await db.commit()
    await svc.notifier.send("Kill switch reset")
