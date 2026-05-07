from __future__ import annotations

import logging
import math
import secrets
import time
from threading import Lock
from typing import Any

from app.clients.backend import BackendClient
from app.registry.service import RegistryService
from app.registry.store import ModelNotFound

from .schemas import EvaluationMetrics, EvaluationReport

log = logging.getLogger(__name__)


class EvaluationNotFound(Exception):
    pass


class BacktestNotFound(Exception):
    pass


_PASS_PRECISION = 0.5


def _evaluation_id() -> str:
    return f"eval-{int(time.time() * 1000):013x}{secrets.token_hex(4)}"


def _stddev(xs: list[float]) -> float:
    if len(xs) < 2:
        return 0.0
    mean = sum(xs) / len(xs)
    var = sum((x - mean) ** 2 for x in xs) / (len(xs) - 1)
    return math.sqrt(var)


def _split_half_drift(returns: list[float]) -> float:
    if len(returns) < 4:
        return 0.0
    mid = len(returns) // 2
    a, b = returns[:mid], returns[mid:]
    mean_a = sum(a) / len(a)
    mean_b = sum(b) / len(b)
    sd = _stddev(returns)
    if sd == 0.0:
        return 0.0
    return abs(mean_a - mean_b) / sd


def compute_metrics(backtest: dict[str, Any]) -> EvaluationMetrics:
    """Pure deterministic metric computation.

    Inputs:
      - backtest['trades'][i]['realized_pl']  (decimal-as-string)
      - backtest['equity_curve'][i]['equity'] (decimal-as-string)
    """
    trades = backtest.get("trades") or []
    closed = [t for t in trades if str(t.get("realized_pl", "0")) not in ("0", "0.0", "")]
    winning = sum(1 for t in closed if float(t["realized_pl"]) > 0)
    losing = sum(1 for t in closed if float(t["realized_pl"]) <= 0)
    total = len(closed)

    precision = (winning / total) if total else 0.0

    curve = backtest.get("equity_curve") or []
    equities = [float(p["equity"]) for p in curve]
    returns: list[float] = []
    positive_bars = 0
    for prev, cur in zip(equities, equities[1:]):
        if prev <= 0:
            continue
        r = (cur - prev) / prev
        returns.append(r)
        if r > 0:
            positive_bars += 1

    recall = (winning / positive_bars) if positive_bars else 0.0
    calibration_error = abs(precision - 0.5)
    feature_drift = _split_half_drift(returns)

    return EvaluationMetrics(
        total_trades=total,
        winning_trades=winning,
        losing_trades=losing,
        precision=precision,
        recall=recall,
        calibration_error=calibration_error,
        feature_drift=feature_drift,
    )


class EvaluationService:
    """Evaluates a registered model against a Go-backend backtest result.

    Stateless beyond an in-process report cache keyed by evaluation id; the
    Go backend remains the source of truth for backtest data.
    """

    def __init__(
        self,
        *,
        backend: BackendClient,
        registry: RegistryService,
    ) -> None:
        self._backend = backend
        self._registry = registry
        self._lock = Lock()
        self._reports: dict[str, EvaluationReport] = {}

    async def run(self, *, backtest_id: str, model_id: str) -> EvaluationReport:
        try:
            self._registry.get(model_id)
        except ModelNotFound as e:
            raise ModelNotFound(f"model {model_id} not registered") from e

        backtest = await self._backend.fetch_backtest(backtest_id)
        if not backtest:
            raise BacktestNotFound(backtest_id)

        metrics = compute_metrics(backtest)
        passed = metrics.total_trades > 0 and metrics.precision >= _PASS_PRECISION
        reason = (
            f"precision {metrics.precision:.3f} >= {_PASS_PRECISION:.2f}"
            if passed
            else (
                "no closed trades"
                if metrics.total_trades == 0
                else f"precision {metrics.precision:.3f} below {_PASS_PRECISION:.2f}"
            )
        )

        cfg = backtest.get("config") or {}
        report = EvaluationReport(
            id=_evaluation_id(),
            backtest_id=backtest_id,
            model_id=model_id,
            symbol=str(cfg.get("symbol") or backtest.get("symbol") or ""),
            interval=str(cfg.get("interval") or backtest.get("interval") or ""),
            metrics=metrics,
            passed=passed,
            reason=reason,
            created_at_ms=int(time.time() * 1000),
        )

        with self._lock:
            self._reports[report.id] = report

        if passed:
            try:
                self._registry.mark_evaluated(model_id, True)
            except ModelNotFound:
                pass

        log.info(
            "evaluation complete",
            extra={
                "evaluation_id": report.id,
                "model_id": model_id,
                "backtest_id": backtest_id,
                "precision": metrics.precision,
                "passed": passed,
            },
        )
        return report

    def get(self, evaluation_id: str) -> EvaluationReport:
        with self._lock:
            rep = self._reports.get(evaluation_id)
        if rep is None:
            raise EvaluationNotFound(evaluation_id)
        return rep

    def list(self) -> list[EvaluationReport]:
        with self._lock:
            return sorted(self._reports.values(), key=lambda r: r.created_at_ms)
