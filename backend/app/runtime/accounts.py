"""Per-account runtime objects: adapter (keys decrypted here, never in the API), circuit
breakers, order manager, reconciler. Built lazily and cached."""

import asyncio
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field, replace
from typing import Any

import structlog
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.auth.crypto import EnvelopeCipher
from app.core.config import Settings
from app.core.models import ExchangeAccount
from app.core.models import RiskProfile as RiskProfileRow
from app.exchange.binance_testnet import ENVIRONMENTS, BinanceTestnetAdapter
from app.exchange.trading import TradingAdapter
from app.execution.order_manager import OrderManager
from app.execution.pg_store import PgExecutionStore
from app.execution.reconciler import Reconciler
from app.risk import CircuitBreakers, RiskEngine, RiskProfile

log = structlog.get_logger()
MANUAL = None  # the API's own (.env) account has no row


def profile_from_row(row: RiskProfileRow | None) -> RiskProfile:
    """The editable limits come from the bot's risk profile; the rest keep SPEC defaults."""
    base = RiskProfile()
    if row is None:
        return base
    return replace(
        base,
        risk_per_trade=row.risk_per_trade,
        max_positions=row.max_positions,
        max_symbol_exposure=row.max_symbol_exposure,
        max_total_exposure=row.max_total_exposure,
        max_open_risk=row.max_open_risk,
        max_bucket_risk=row.max_bucket_risk,
        min_cash_reserve=row.min_cash_reserve,
        daily_loss=row.daily_loss,
        weekly_loss=row.weekly_loss,
        max_drawdown=row.max_dd,
    )


@dataclass(slots=True)
class AccountRuntime:
    account_id: uuid.UUID | None
    adapter: TradingAdapter
    store: PgExecutionStore
    breakers: CircuitBreakers
    profile: RiskProfile
    manager: OrderManager
    reconciler: Reconciler
    kill_handled: bool = False
    # one writer at a time per account: entries, exits, the reconciler and the kill switch all
    # change the same positions/orders, and must never interleave (e.g. the reconciler
    # re-placing a stop the kill switch has just cancelled)
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)


AdapterFactory = Callable[[ExchangeAccount | None], TradingAdapter | None]


def binance_adapter_factory(settings: Settings) -> AdapterFactory:
    """Real adapters. The only hosts reachable are demo/testnet (the adapter refuses the rest)."""
    base = ENVIRONMENTS[settings.binance_trading_env]
    cipher: EnvelopeCipher | None = None

    def make(row: ExchangeAccount | None) -> TradingAdapter | None:
        nonlocal cipher
        if row is None:  # the .env account used for manual orders
            key = settings.binance_api_key.get_secret_value()
            secret = settings.binance_api_secret.get_secret_value()
            return BinanceTestnetAdapter(key, secret, base_url=base) if key and secret else None
        cipher = cipher or EnvelopeCipher.from_b64(settings.master_key.get_secret_value())
        key = cipher.decrypt(row.api_key_enc, aad=f"account:{row.id}:key".encode()).decode()
        secret = cipher.decrypt(
            row.api_secret_enc, aad=f"account:{row.id}:secret".encode()
        ).decode()
        return BinanceTestnetAdapter(key, secret, base_url=base)

    return make


class AccountPool:
    def __init__(
        self,
        sessions: async_sessionmaker[AsyncSession],
        store: PgExecutionStore,
        adapter_factory: AdapterFactory,
        profile: RiskProfile | None = None,
        **manager_kw: Any,
    ) -> None:
        self.sessions, self._store, self._factory = sessions, store, adapter_factory
        self._profile = profile
        self._manager_kw = manager_kw
        self._cache: dict[uuid.UUID | None, AccountRuntime] = {}

    async def get(
        self, account_id: uuid.UUID | None, profile_row: RiskProfileRow | None = None
    ) -> AccountRuntime | None:
        """``None`` when the account has no usable credentials (e.g. no .env key)."""
        if account_id in self._cache:
            return self._cache[account_id]
        row: ExchangeAccount | None = None
        if account_id is not None:
            async with self.sessions() as db:
                row = await db.get(ExchangeAccount, account_id)
            if row is None:
                return None
        adapter = self._factory(row)
        if adapter is None:
            return None
        profile = self._profile or profile_from_row(profile_row)
        breakers = CircuitBreakers(profile)
        store = self._store.for_account(account_id)
        manager = OrderManager(adapter, RiskEngine(profile, breakers), store, **self._manager_kw)
        rt = AccountRuntime(
            account_id,
            adapter,
            store,
            breakers,
            profile,
            manager,
            Reconciler(adapter, store, manager),
        )
        self._cache[account_id] = rt
        return rt

    def runtimes(self) -> list[AccountRuntime]:
        return list(self._cache.values())

    async def aclose(self) -> None:
        for rt in self._cache.values():
            close = getattr(rt.adapter, "aclose", None)
            if close is not None:
                await close()
