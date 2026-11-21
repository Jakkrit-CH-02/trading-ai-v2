import contextlib
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime

from fastapi import FastAPI
from redis.asyncio import Redis
from sqlalchemy import func, select
from sqlalchemy.exc import SQLAlchemyError

from app.api import (
    accounts,
    backtests,
    bots,
    health,
    risk_routes,
    settings_routes,
    v1,
    ws,
)
from app.api import (
    orders as orders_api,
)
from app.api.services import BinanceMarketGateway, Services
from app.auth import routes as auth_routes
from app.core.config import Settings, get_settings
from app.core.db import make_engine, make_session_factory
from app.core.logging import configure_logging
from app.core.models import Bot, BotStatus
from app.exchange.binance_testnet import ENVIRONMENTS, BinanceTestnetAdapter
from app.execution.pg_store import PgExecutionStore
from app.marketdata.store import PgCandleStore
from app.notify.telegram import make_notifier


def build_services(settings: Settings) -> Services:
    """Production wiring. Trading is optional: without demo/testnet keys the dashboard shows
    its "not connected" state instead of failing."""
    factory = make_session_factory(make_engine(settings.database_url))
    key, secret = (
        settings.binance_api_key.get_secret_value(),
        settings.binance_api_secret.get_secret_value(),
    )
    trading = (
        BinanceTestnetAdapter(key, secret, base_url=ENVIRONMENTS[settings.binance_trading_env])
        if key and secret
        else None
    )
    market = BinanceMarketGateway(settings.binance_rest_url, settings.fng_url)
    notifier = make_notifier(
        settings.telegram_bot_token.get_secret_value(), settings.telegram_chat_id
    )
    return Services(
        settings=settings,
        candles=PgCandleStore(factory),
        market=market,
        trading=trading,
        db=factory,
        notifier=notifier,
        exec_store=PgExecutionStore(factory),
        redis=Redis.from_url(settings.redis_url, decode_responses=True),
    )


async def restore_kill_state(svc: Services) -> None:
    """Fail safe across restarts: if any bot is KILLED in the database, the kill switch is
    latched again (the in-memory breaker would otherwise silently forget it)."""
    if svc.db is None:
        return
    try:
        async with svc.db() as db:
            killed = (
                await db.execute(
                    select(func.count()).select_from(Bot).where(Bot.status == BotStatus.KILLED)
                )
            ).scalar_one()
    except (OSError, SQLAlchemyError):
        return  # no database yet (e.g. first start before migrations); nothing to restore
    if killed:
        svc.risk_breakers().trigger_kill(datetime.now(UTC), "restored after restart")


def create_app(services: Services | None = None) -> FastAPI:
    settings = get_settings()
    configure_logging(settings.service_name)
    if settings.env != "dev":
        secret = settings.jwt_secret.get_secret_value()
        if secret.startswith("change-me") or len(secret) < 32:
            raise RuntimeError("JWT_SECRET must be a random value of at least 32 characters")

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        if services is None:
            app.state.services = build_services(settings)
        await restore_kill_state(app.state.services)
        with contextlib.suppress(OSError, SQLAlchemyError):
            await backtests.fail_interrupted(app.state.services)
        yield
        svc: Services = app.state.services
        await svc.market.aclose()
        if svc.redis is not None:
            await svc.redis.aclose()
        if svc.trading is not None:
            await svc.trading.aclose()

    app = FastAPI(title="Softtrade API", version="0.1.0", lifespan=lifespan)
    if services is not None:
        app.state.services = services
    app.include_router(health.router)
    app.include_router(auth_routes.router)
    app.include_router(v1.router)
    app.include_router(bots.router)
    app.include_router(risk_routes.router)
    app.include_router(accounts.router)
    app.include_router(backtests.router)
    app.include_router(orders_api.router)
    app.include_router(settings_routes.router)
    app.include_router(ws.router)
    return app


app = create_app()
