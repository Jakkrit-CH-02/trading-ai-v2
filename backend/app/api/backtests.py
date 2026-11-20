import asyncio
from datetime import datetime
from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy import select, update

from app.api.bots import validate_config
from app.api.services import Services, get_services
from app.auth.audit import audit
from app.auth.deps import CurrentUser, Db, client_ip, current_user
from app.backtest.jobs import BacktestRequest, execute, load_frames
from app.core.models import Backtest

router = APIRouter(
    prefix="/api/v1/backtests", dependencies=[Depends(current_user)], tags=["backtests"]
)
Svc = Annotated[Services, Depends(get_services)]


class BacktestOut(BaseModel):
    id: UUID
    status: str
    created_at: datetime
    request: dict[str, Any]
    result: dict[str, Any] | None = None
    error: str | None = None


def to_out(b: Backtest, with_result: bool = True) -> BacktestOut:
    m = b.metrics or {}
    return BacktestOut(
        id=b.id,
        status=b.status,
        created_at=b.created_at,
        request=b.strategy_config_snapshot,
        result=m.get("result") if with_result else None,
        error=m.get("error"),
    )


async def run_job(svc: Services, job_id: UUID, req: BacktestRequest) -> None:
    """One job at a time (CPU bound); status and result live in the ``backtests`` row."""
    assert svc.db
    async with svc.job_lock:
        async with svc.db() as db:
            await db.execute(update(Backtest).where(Backtest.id == job_id).values(status="RUNNING"))
            await db.commit()
        status, payload = "DONE", {}
        try:
            frames = await load_frames(svc.candles, req.symbols, req.years)
            result = await asyncio.to_thread(execute, frames, req)
            payload = {
                "walk_forward": result["walk_forward"],
                "gate1": result["gate1"],
                "result": result,
            }
        except Exception as e:
            status, payload = "FAILED", {"error": f"{type(e).__name__}: {e}"}
        async with svc.db() as db:
            await db.execute(
                update(Backtest).where(Backtest.id == job_id).values(status=status, metrics=payload)
            )
            await db.commit()


@router.post("", response_model=BacktestOut, status_code=202)
async def submit(
    body: BacktestRequest, user: CurrentUser, request: Request, svc: Svc, db: Db
) -> BacktestOut:
    validate_config(svc, body.strategy, body.params, body.symbols)
    row = Backtest(
        strategy_config_snapshot={
            "strategy": body.strategy,
            "params": body.params,
            "symbols": body.symbols,
            "years": body.years,
            "walk_forward": body.walk_forward,
        },
        range={"years": body.years},
        fees_model={"taker": body.fee, "slippage": body.slippage},
        status="PENDING",
    )
    db.add(row)
    await db.flush()
    audit(
        db,
        user.user_id,
        "backtest.submit",
        f"backtest:{row.id}",
        after=row.strategy_config_snapshot,
        ip=client_ip(request),
    )
    await db.commit()
    task = asyncio.create_task(run_job(svc, row.id, body))
    svc.tasks.add(task)  # keep a reference so the task is not garbage collected
    task.add_done_callback(svc.tasks.discard)
    return to_out(row)


@router.get("", response_model=list[BacktestOut])
async def list_runs(db: Db, limit: int = 20) -> list[BacktestOut]:
    rows = (
        await db.execute(
            select(Backtest).order_by(Backtest.created_at.desc()).limit(min(limit, 100))
        )
    ).scalars()
    return [to_out(r, with_result=False) for r in rows]


@router.get("/{job_id}", response_model=BacktestOut)
async def read_run(job_id: UUID, db: Db) -> BacktestOut:
    row = await db.get(Backtest, job_id)
    if row is None:
        raise HTTPException(404, "backtest not found")
    return to_out(row)


async def fail_interrupted(svc: Services) -> None:
    """Jobs left PENDING/RUNNING by a previous process can never finish: mark them failed."""
    if svc.db is None:
        return
    async with svc.db() as db:
        await db.execute(
            update(Backtest)
            .where(Backtest.status.in_(("PENDING", "RUNNING")))
            .values(status="FAILED", metrics={"error": "interrupted by a restart"})
        )
        await db.commit()
