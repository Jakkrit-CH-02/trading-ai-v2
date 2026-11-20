from typing import Annotated

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from app.api.services import Services, get_services
from app.auth.deps import CurrentUser, current_user
from app.notify.telegram import NullNotifier

router = APIRouter(
    prefix="/api/v1/settings", dependencies=[Depends(current_user)], tags=["settings"]
)
Svc = Annotated[Services, Depends(get_services)]


class NotificationsOut(BaseModel):
    telegram_configured: bool
    live_trading_enabled: bool
    trading_env: str


@router.get("/notifications", response_model=NotificationsOut)
async def notifications(svc: Svc) -> NotificationsOut:
    """Never returns the token or chat id: only whether alerts can be delivered."""
    return NotificationsOut(
        telegram_configured=not isinstance(svc.notifier, NullNotifier),
        live_trading_enabled=not svc.settings.binance_testnet_only,
        trading_env=svc.settings.binance_trading_env,
    )


@router.post("/notifications/test", status_code=204)
async def test_notification(user: CurrentUser, svc: Svc) -> None:
    await svc.notifier.send("Softtrade test alert")
