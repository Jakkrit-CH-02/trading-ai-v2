"""S_ml models (SPEC 4.1): what is trained, what is active and why, and the rollback button."""

from datetime import datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy import select

from app.api.services import Services, get_services
from app.auth.audit import audit
from app.auth.deps import Db, TotpUser, client_ip, current_user
from app.core.models import MlModel
from app.ml.registry import rollback

router = APIRouter(prefix="/api/v1/ml", dependencies=[Depends(current_user)], tags=["ml"])
Svc = Annotated[Services, Depends(get_services)]
STRATEGIES = ("S1", "S2", "S3")


class MlModelOut(BaseModel):
    strategy: str
    version: int
    status: str
    created_at: datetime
    trained_from: datetime
    trained_to: datetime
    n_samples: int
    cv_auc: float | None
    holdout_auc: float | None
    backtest: dict[str, Any] | None
    reason: str | None
    note: str | None


def out(m: MlModel) -> MlModelOut:
    met = m.metrics or {}
    return MlModelOut(
        strategy=m.strategy, version=m.version, status=m.status, created_at=m.created_at,
        trained_from=m.trained_from, trained_to=m.trained_to, n_samples=m.n_samples,
        cv_auc=(met.get("cv") or {}).get("auc"), holdout_auc=(met.get("holdout") or {}).get("auc"),
        backtest=met.get("backtest"), reason=(met.get("promotion") or {}).get("reason"),
        note=m.note,
    )  # fmt: skip


@router.get("/models", response_model=list[MlModelOut])
async def models(db: Db) -> list[MlModelOut]:
    """Every stored version, newest first (the active one is marked by its status)."""
    rows = (
        await db.execute(select(MlModel).order_by(MlModel.strategy, MlModel.version.desc()))
    ).scalars()
    return [out(m) for m in rows]


@router.post("/{strategy}/rollback", response_model=MlModelOut)
async def roll_back(
    strategy: str, user: TotpUser, request: Request, svc: Svc, db: Db
) -> MlModelOut:
    """Re-activate the previous version (needs 2FA). If none exists S_ml simply stays as it is."""
    strategy = strategy.upper()
    if strategy not in STRATEGIES or svc.db is None:
        raise HTTPException(404, "unknown strategy")
    m = await rollback(svc.db, strategy)
    if m is None:
        raise HTTPException(409, "there is no earlier version to roll back to")
    audit(db, user.user_id, "ml.rollback", f"ml:{strategy}", after={"version": m.version},
          ip=client_ip(request))  # fmt: skip
    await db.commit()
    return out(m)
