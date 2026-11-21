"""Strategy lookup + a single entry point that picks the right simulator."""

from dataclasses import fields, replace
from decimal import Decimal
from typing import Any

from app.backtest.engine import BacktestConfig, BacktestResult, run_backtest
from app.backtest.grid import run_grid_backtest
from app.strategies.base import Strategy
from app.strategies.params import S1Params, S2Params, S3Params, S4Params, S5Params
from app.strategies.s1_trend import S1Trend
from app.strategies.s2_meanrev import S2MeanReversion
from app.strategies.s3_breakout import S3Breakout
from app.strategies.s4_grid import S4Grid
from app.strategies.s5_donchian import S5Donchian

AnyStrategy = Strategy | S4Grid

_FACTORIES: dict[str, tuple[Any, Any]] = {
    "s1": (S1Trend, S1Params),
    "s2": (S2MeanReversion, S2Params),
    "s3": (S3Breakout, S3Params),
    "s4": (S4Grid, S4Params),
    "s5": (S5Donchian, S5Params),
}


def strategy_names() -> list[str]:
    return sorted(_FACTORIES)


def default_params(name: str) -> Any:
    return _FACTORIES[name][1]()


def make_strategy(name: str, overrides: dict[str, Any] | None = None) -> AnyStrategy:
    """Build a strategy with default SPEC parameters, optionally overriding top-level fields."""
    if name not in _FACTORIES:
        raise ValueError(f"unknown strategy {name!r}; choose from {strategy_names()}")
    cls, params_cls = _FACTORIES[name]
    params = params_cls()
    if overrides:
        unknown = set(overrides) - {f.name for f in fields(params)}
        if unknown:
            raise ValueError(f"unknown parameters for {name}: {sorted(unknown)}")
        params = replace(params, **overrides)
    strategy: AnyStrategy = cls(params)
    return strategy


def run_strategy(
    strategy: AnyStrategy,
    feats: Any,
    cfg: BacktestConfig | None = None,
    start: int = 0,
    end: int | None = None,
    initial_equity: Decimal | None = None,
) -> BacktestResult:
    if isinstance(strategy, S4Grid):
        return run_grid_backtest(strategy, feats, cfg, start, end, initial_equity)
    return run_backtest(strategy, feats, cfg, start, end, initial_equity)
