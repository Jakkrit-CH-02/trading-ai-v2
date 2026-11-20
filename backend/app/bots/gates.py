"""Go-live gate (SPEC 11): a bot may only trade real money after a passing out-of-sample backtest
(gate 1) and a clean paper run (gate 2). Pure logic so it is trivially testable."""

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

PAPER_MIN_DAYS = 28
MAX_PAPER_DEVIATION = 0.30


@dataclass(frozen=True, slots=True)
class GateCheck:
    name: str
    ok: bool
    detail: str


@dataclass(frozen=True, slots=True)
class GoLiveStatus:
    allowed: bool
    checks: tuple[GateCheck, ...]


def snapshot_matches(
    snap: dict[str, Any], strategy: str, params: dict[str, Any], symbols: list[str]
) -> bool:
    """A backtest only counts for a bot when strategy, parameters and symbols are identical."""
    return (
        snap.get("strategy") == strategy
        and (snap.get("params") or {}) == params
        and sorted(snap.get("symbols") or []) == sorted(symbols)
    )


def evaluate_go_live(
    *,
    gate1_passed: bool | None,
    gate1_failures: list[str],
    paper_started_at: datetime | None,
    now: datetime,
    paper_deviation: float | None,
    unhandled_order_errors: int,
    recon_mismatches: int,
    testnet_only: bool,
) -> GoLiveStatus:
    checks: list[GateCheck] = []

    if gate1_passed is None:
        checks.append(
            GateCheck("gate1_backtest", False, "no walk-forward backtest for this exact config")
        )
    else:
        detail = "passed (out-of-sample)" if gate1_passed else "; ".join(gate1_failures) or "failed"
        checks.append(GateCheck("gate1_backtest", gate1_passed, detail))

    if paper_started_at is None:
        checks.append(GateCheck("gate2_paper_duration", False, "paper trading has not started"))
    else:
        days = (now - paper_started_at) / timedelta(days=1)
        checks.append(
            GateCheck(
                "gate2_paper_duration",
                days >= PAPER_MIN_DAYS,
                f"{days:.1f} of {PAPER_MIN_DAYS} days",
            )
        )
    if paper_deviation is None:
        checks.append(GateCheck("gate2_deviation", False, "no paper-vs-backtest comparison yet"))
    else:
        checks.append(
            GateCheck(
                "gate2_deviation",
                paper_deviation <= MAX_PAPER_DEVIATION,
                f"{paper_deviation:.0%} vs max {MAX_PAPER_DEVIATION:.0%}",
            )
        )
    checks.append(
        GateCheck(
            "gate2_order_errors", unhandled_order_errors == 0, f"{unhandled_order_errors} unhandled"
        )
    )
    checks.append(
        GateCheck("gate2_reconciliation", recon_mismatches == 0, f"{recon_mismatches} mismatches")
    )
    # SPEC 12 / CLAUDE.md: before Gate B only Testnet/Demo is allowed, whatever the other gates say.
    checks.append(
        GateCheck(
            "gate_b_live_enabled",
            not testnet_only,
            "live trading is disabled (BINANCE_TESTNET_ONLY) until Gate B"
            if testnet_only
            else "enabled",
        )
    )
    return GoLiveStatus(all(c.ok for c in checks), tuple(checks))
