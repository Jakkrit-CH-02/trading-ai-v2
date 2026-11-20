from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api import health, v1, ws
from app.api.services import BinanceMarketGateway, Services
from app.core.config import Settings, get_settings
from app.core.db import make_engine, make_session_factory
from app.core.logging import configure_logging
from app.exchange.binance_testnet import ENVIRONMENTS, BinanceTestnetAdapter
from app.marketdata.store import PgCandleStore


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
    return Services(
        settings=settings, candles=PgCandleStore(factory), market=market, trading=trading
    )


def create_app(services: Services | None = None) -> FastAPI:
    settings = get_settings()
    configure_logging(settings.service_name)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        if services is None:
            app.state.services = build_services(settings)
        yield
        svc: Services = app.state.services
        await svc.market.aclose()
        if svc.trading is not None:
            await svc.trading.aclose()

    app = FastAPI(title="Softtrade API", version="0.1.0", lifespan=lifespan)
    if services is not None:
        app.state.services = services
    app.include_router(health.router)
    app.include_router(v1.router)
    app.include_router(ws.router)
    return app


app = create_app()
