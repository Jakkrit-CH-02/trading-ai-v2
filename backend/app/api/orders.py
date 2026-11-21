"""Manual orders (SPEC 8.1 / 10 page 2). They go through the same Risk Engine and OrderManager
as bot orders; the user only supplies direction, entry and stop, never the size."""

from datetime import UTC, datetime
from decimal import Decimal
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field

from app.api.schemas import DepthLevel
from app.api.services import Services, get_services
from app.auth.audit import audit
from app.auth.deps import CurrentUser, Db, client_ip, current_user
from app.core.models import BotStatus, Side
from app.exchange.errors import ExchangeError, UnknownOrder
from app.execution.order_manager import OrderManager
from app.execution.portfolio import build_portfolio
from app.execution.types import ExecStatus
from app.risk import RiskEngine
from app.risk.types import MarketState, PortfolioState, RiskDecision, TradeIntent

router = APIRouter(prefix="/api/v1/orders", dependencies=[Depends(current_user)], tags=["orders"])
Svc = Annotated[Services, Depends(get_services)]
ZERO = Decimal(0)


class OrderIn(BaseModel):
    symbol: str
    order_type: Literal["LIMIT", "MARKET"] = "LIMIT"
    entry: Decimal | None = Field(
        None, gt=0, description="Required for LIMIT; MARKET uses the last price"
    )
    stop: Decimal = Field(gt=0)
    tp1: Decimal | None = Field(None, gt=0)


class CheckOut(BaseModel):
    name: str
    passed: bool
    detail: str


class PreviewOut(BaseModel):
    approved: bool
    qty: Decimal
    notional: Decimal
    risk_amount: Decimal
    risk_pct_of_equity: Decimal
    entry: Decimal
    stop: Decimal
    tp1: Decimal | None
    reasons: list[str]
    checks: list[CheckOut]
    adjustments: list[str]


class OrderResult(BaseModel):
    status: str
    detail: str
    client_order_id: str | None
    preview: PreviewOut | None


def walk_asks(asks: list[DepthLevel], budget: Decimal) -> Decimal:
    """Expected slippage in bps of buying ``budget`` USDT against the ask side. A book too
    thin to fill it counts as unlimited slippage, which the Risk Engine then refuses."""
    if not asks or budget <= 0:
        return Decimal(10_000)
    best, spent, qty = asks[0].price, ZERO, ZERO
    for lvl in asks:
        take = min(lvl.qty, (budget - spent) / lvl.price)
        spent += take * lvl.price
        qty += take
        if spent >= budget:
            return (spent / qty - best) / best * 10_000
    return Decimal(10_000)


async def evaluate(
    svc: Services, body: OrderIn
) -> tuple[OrderIn, RiskDecision, TradeIntent, PortfolioState, MarketState]:
    if svc.trading is None:
        raise HTTPException(409, "no trading account configured")
    symbol = body.symbol.upper()
    if symbol not in svc.settings.symbols:
        raise HTTPException(404, f"unknown symbol {symbol}")
    if body.order_type == "LIMIT" and body.entry is None:
        raise HTTPException(422, "entry price is required for LIMIT orders")
    now = datetime.now(UTC)
    try:
        ticks = await svc.market.tickers(svc.settings.symbols)
        balances = await svc.trading.balances()
    except Exception as e:
        raise HTTPException(502, "market data or exchange unavailable") from e
    last = ticks[symbol].last
    entry = body.entry if body.order_type == "LIMIT" and body.entry is not None else last
    br = svc.risk_breakers()
    br.record_tick(now)  # the quotes above were fetched a moment ago: data is fresh
    pf = await build_portfolio(
        balances,
        {sym: t.last for sym, t in ticks.items()},
        svc.exec_store,
        day_start=svc.day_start.equity,
    )
    cash, equity = pf.cash, pf.equity
    mk = MarketState(now=now, bot_status=BotStatus.RUNNING, data_age_s=0.0, clock_drift_ms=0.0)
    slippage: Decimal | None = None
    if body.order_type == "MARKET":
        # worst case: the largest position the profile allows, bought by walking the ask side
        budget = min(cash, equity * svc.profile.max_symbol_exposure)
        try:
            slippage = walk_asks((await svc.market.depth(symbol, 20)).asks, budget)
        except Exception as e:
            raise HTTPException(502, "order book unavailable") from e
    intent = TradeIntent(
        symbol=symbol,
        side=Side.BUY,
        entry=entry,
        stop=body.stop,
        tp1=body.tp1,
        order_type=body.order_type,
        is_manual=True,
        expected_slippage_bps=slippage,
    )
    filters = await svc.trading.symbol_filters(symbol)
    decision = RiskEngine(svc.profile, br).evaluate(intent, pf, mk, filters)
    return body, decision, intent, pf, mk


def preview_out(d: RiskDecision, equity: Decimal) -> PreviewOut:
    return PreviewOut(
        approved=d.approved,
        qty=d.qty,
        notional=d.notional,
        risk_amount=d.risk_amount,
        risk_pct_of_equity=(d.risk_amount / equity * 100).quantize(Decimal("0.0001"))
        if equity > 0
        else ZERO,
        entry=d.entry,
        stop=d.stop,
        tp1=d.tp1,
        reasons=[r.value for r in d.reasons],
        checks=[CheckOut(name=c.name, passed=c.passed, detail=c.detail) for c in d.checks],
        adjustments=list(d.adjustments),
    )


@router.post("/preview", response_model=PreviewOut)
async def preview(body: OrderIn, svc: Svc) -> PreviewOut:
    """Dry run through the Risk Engine: size, risk as % of the portfolio and every check."""
    _, d, _, pf, _ = await evaluate(svc, body)
    return preview_out(d, pf.equity)


@router.post("", response_model=OrderResult, status_code=201)
async def place(
    body: OrderIn, user: CurrentUser, request: Request, svc: Svc, db: Db
) -> OrderResult:
    _, d, intent, pf, mk = await evaluate(svc, body)
    prev = preview_out(d, pf.equity)
    if not d.approved:  # refuse here too: nothing is sent when the Risk Engine says no
        audit(
            db,
            user.user_id,
            "order.rejected",
            f"order:{intent.symbol}",
            after={"reasons": prev.reasons},
            ip=client_ip(request),
        )
        await db.commit()
        return OrderResult(
            status=ExecStatus.REJECTED.value,
            detail=",".join(prev.reasons),
            client_order_id=None,
            preview=prev,
        )
    assert svc.trading is not None
    om = OrderManager(svc.trading, RiskEngine(svc.profile, svc.risk_breakers()), svc.exec_store)
    res = await om.submit(intent, pf, mk)
    audit(
        db,
        user.user_id,
        "order.place",
        f"order:{intent.symbol}",
        after={"status": res.status.value, "qty": str(d.qty), "stop": str(d.stop)},
        ip=client_ip(request),
    )
    await db.commit()
    return OrderResult(
        status=res.status.value,
        detail=res.detail,
        client_order_id=res.client_order_id,
        preview=prev,
    )


@router.delete("/{client_order_id}", status_code=204)
async def cancel(
    client_order_id: str,
    symbol: Annotated[str, Query()],
    user: CurrentUser,
    request: Request,
    svc: Svc,
    db: Db,
) -> None:
    if svc.trading is None:
        raise HTTPException(409, "no trading account configured")
    try:
        await svc.trading.cancel_order(symbol.upper(), client_order_id)
    except UnknownOrder as e:
        raise HTTPException(404, "order not found (already filled or cancelled?)") from e
    except ExchangeError as e:
        raise HTTPException(502, "exchange unavailable") from e
    audit(db, user.user_id, "order.cancel", f"order:{client_order_id}", ip=client_ip(request))
    await db.commit()
