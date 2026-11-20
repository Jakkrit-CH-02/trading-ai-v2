from typing import Any

import pytest

from app.risk import PortfolioState, Reason, RiskConfigError, RiskProfile
from app.risk.limits import LimitOutcome, apply_limits
from app.risk.sizing import (
    effective_risk_pct,
    kelly_fraction,
    position_size,
    quantize_down,
    unit_risk,
)
from tests.risk_helpers import FILTERS, D, make_intent, make_portfolio, position

P = RiskProfile()


# ---- profile bounds --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "kw",
    [
        {"risk_per_trade": D("0.02"), "risk_per_trade_cap": D("0.02")},  # SPEC caps risk at 1%
        {"risk_per_trade": D("0.02")},  # above its own cap
        {"risk_per_trade": D(0)},
        {"kelly_cap_fraction": D("0.5")},
        {"fee_rate": D("0.5")},
        {"max_positions": 0},
        {"max_total_exposure": D("0.9"), "min_cash_reserve": D("0.2")},  # > 100% together
        {"max_symbol_exposure": D("0.9")},  # more than total exposure
        {"max_bucket_risk": D("0.03")},  # more than total open risk
        {"daily_loss": D("0.10")},  # daily above weekly
        {"weekly_loss": D("0.2")},  # weekly above max drawdown
        {"min_rr": D("0.5")},
        {"loss_streak": 0},
        {"min_cash_reserve": D(0)},
    ],
)
def test_profile_rejects_settings_that_loosen_the_spec(kw: dict[str, object]) -> None:
    with pytest.raises(RiskConfigError):
        RiskProfile(**kw)  # type: ignore[arg-type]


def test_profile_defaults_are_the_spec_values() -> None:
    assert (P.risk_per_trade, P.max_positions, P.max_symbol_exposure) == (D("0.005"), 4, D("0.25"))
    assert (P.max_total_exposure, P.max_open_risk, P.max_bucket_risk) == (
        D("0.80"),
        D("0.02"),
        D("0.0125"),
    )
    assert (P.min_cash_reserve, P.daily_loss, P.weekly_loss, P.max_drawdown) == (
        D("0.20"), D("0.02"), D("0.05"), D("0.12"),
    )  # fmt: skip
    assert (P.loss_streak, P.streak_recovery_wins, P.min_rr) == (4, 2, D("1.5"))


# ---- sizing ----------------------------------------------------------------------------------


def test_position_size_matches_the_spec_formula() -> None:
    s = position_size(D(10_000), D("0.005"), D(1), D(1), D(100), D(98), FILTERS, P)
    ur = D(2) + (D(100) + D(98)) * (D("0.001") + D("0.0005"))
    assert s.unit_risk == ur and s.risk_amount == D(50)
    assert s.qty == quantize_down(D(50) / ur, D("0.00001"))
    assert s.notional == s.qty * D(100)
    assert s.qty * (D(100) - D(98)) <= s.risk_amount  # rounding down can only reduce risk


def test_factors_scale_the_position() -> None:
    full = position_size(D(10_000), D("0.005"), D(1), D(1), D(100), D(98), FILTERS, P)
    half_score = position_size(D(10_000), D("0.005"), D(1), D("0.5"), D(100), D(98), FILTERS, P)
    half_regime = position_size(D(10_000), D("0.005"), D("0.5"), D(1), D(100), D(98), FILTERS, P)
    assert half_score.qty == quantize_down(full.qty / 2, D("0.00001")) or abs(
        half_score.qty - full.qty / 2
    ) <= D("0.00001")
    assert half_regime.qty == half_score.qty


def test_wider_stop_means_smaller_position() -> None:
    near = position_size(D(10_000), D("0.005"), D(1), D(1), D(100), D(99), FILTERS, P)
    far = position_size(D(10_000), D("0.005"), D(1), D(1), D(100), D(90), FILTERS, P)
    assert far.qty < near.qty


@pytest.mark.parametrize(
    "equity,entry,stop,risk",
    [(0, 100, 98, "0.005"), (1000, 0, 98, "0.005"), (1000, 100, 0, "0.005"), (1000, 100, 98, "0")],
)
def test_degenerate_inputs_size_to_zero(equity: int, entry: int, stop: int, risk: str) -> None:
    s = position_size(D(equity), D(risk), D(1), D(1), D(entry), D(stop), FILTERS, P)
    assert s.qty == 0 and s.notional == 0


def test_zero_factor_sizes_to_zero_and_max_qty_is_respected() -> None:
    assert position_size(D(10_000), D("0.005"), D(0), D(1), D(100), D(98), FILTERS, P).qty == 0
    tiny_cap = FILTERS.__class__(D("0.01"), D("0.001"), D("0.001"), D("1.5"), D(10))
    assert position_size(D(10_000), D("0.005"), D(1), D(1), D(100), D(98), tiny_cap, P).qty == D(
        "1.5"
    )


def test_quantize_down_never_rounds_up_and_rejects_bad_step() -> None:
    assert quantize_down(D("1.23999"), D("0.01")) == D("1.23")
    assert quantize_down(D("0.009"), D("0.01")) == 0
    with pytest.raises(ValueError, match="step"):
        quantize_down(D(1), D(0))


def test_unit_risk_includes_distance_fees_and_slippage() -> None:
    assert unit_risk(D(100), D(98), D(0), D(0)) == 2
    assert unit_risk(D(100), D(98), D("0.001"), D("0.0005")) == D(2) + D(198) * D("0.0015")


def test_kelly_is_only_a_ceiling() -> None:
    assert kelly_fraction(D("0.5"), D(2)) == D("0.25")
    assert kelly_fraction(D("0.3"), D(1)) == 0  # negative edge -> no allocation
    assert kelly_fraction(D("0.6"), D(0)) == 0
    assert effective_risk_pct(P) == D("0.005")
    assert effective_risk_pct(P, kelly=D("0.4")) == D("0.005")  # 1/4 Kelly = 10%: base wins
    assert effective_risk_pct(P, kelly=D("0.01")) == D("0.0025")  # 1/4 Kelly = 0.25%: ceiling bites
    assert effective_risk_pct(P, multiplier=D("0.5")) == D("0.0025")
    assert effective_risk_pct(P, multiplier=D(100)) == D("0.01")  # never above the SPEC cap
    assert effective_risk_pct(P, kelly=D(0)) == 0


# ---- exposure limits --------------------------------------------------------------------------


def run(
    pf: PortfolioState, qty: str = "21.76", buckets: dict[str, str] | None = None, **intent: Any
) -> LimitOutcome:
    return apply_limits(make_intent(**intent), D(qty), pf, buckets or {}, P, FILTERS)


def reasons(out: LimitOutcome) -> set[Reason]:
    return {c.reason for c in out.failed if c.reason}


def test_clean_portfolio_passes_every_limit() -> None:
    out = run(make_portfolio())
    assert not out.failed and out.qty == D("21.76") and not out.adjustments


def test_symbol_exposure_reduces_the_size_to_fit() -> None:
    out = run(make_portfolio(positions=(position("BTCUSDT", 2000),)))
    assert not out.failed
    assert out.qty == D("5")  # room = 25% of 10,000 - 2,000 = 500 -> 5 units at 100
    assert out.adjustments and "per-symbol" in out.adjustments[0]


def test_symbol_already_at_cap_is_rejected() -> None:
    out = run(make_portfolio(positions=(position("BTCUSDT", 2500),)))
    assert reasons(out) == {Reason.SYMBOL_EXPOSURE} and out.qty == 0


def test_max_positions_rejects_a_fifth_symbol_but_allows_adding_to_a_held_one() -> None:
    held = tuple(position(s, 500) for s in ("ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT"))
    assert Reason.MAX_POSITIONS in reasons(run(make_portfolio(positions=held)))
    assert Reason.MAX_POSITIONS not in reasons(
        run(make_portfolio(positions=held), symbol="ETHUSDT")
    )


def test_total_exposure_is_a_hard_reject_not_a_reduction() -> None:
    held = tuple(position(s, 2300) for s in ("ETHUSDT", "SOLUSDT", "BNBUSDT"))  # 69%
    out = run(make_portfolio(positions=held, cash=3100))
    assert Reason.TOTAL_EXPOSURE in reasons(out) and out.qty == D("21.76")  # qty untouched


def test_open_risk_limit() -> None:
    held = (position("ETHUSDT", 2000, "0.045"), position("SOLUSDT", 2000, "0.045"))  # 1.8% at risk
    assert Reason.OPEN_RISK in reasons(run(make_portfolio(positions=held)))


def test_unprotected_position_counts_as_fully_at_risk() -> None:
    from app.risk import PositionView

    naked = PositionView("ETHUSDT", D(10), D(100), D(100), None)
    assert naked.open_risk == naked.notional
    assert Reason.OPEN_RISK in reasons(run(make_portfolio(positions=(naked,))))


def test_correlation_bucket_limit_only_applies_within_the_bucket() -> None:
    held = (position("ETHUSDT", 2000, "0.06"),)  # 1.2% open risk in ETH
    same = run(make_portfolio(positions=held), buckets={"BTCUSDT": "L1", "ETHUSDT": "L1"})
    other = run(make_portfolio(positions=held), buckets={"BTCUSDT": "L1", "ETHUSDT": "L2"})
    assert Reason.BUCKET_RISK in reasons(same)
    assert Reason.BUCKET_RISK not in reasons(other)


def test_cash_reserve_and_funds() -> None:
    low_cash = run(make_portfolio(cash=2500))  # pays 2,178 -> 322 left, reserve is 2,000
    assert Reason.CASH_RESERVE in reasons(low_cash) and Reason.INSUFFICIENT_FUNDS not in reasons(
        low_cash
    )
    broke = run(make_portfolio(cash=1000))
    assert {Reason.INSUFFICIENT_FUNDS, Reason.CASH_RESERVE} <= reasons(broke)
