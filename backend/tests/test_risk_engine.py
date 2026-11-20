import json
from datetime import timedelta
from typing import Any

import pytest

from app.core.models import BotStatus, Side
from app.risk import (
    MarketState,
    PortfolioState,
    Reason,
    RiskDecision,
    RiskEngine,
    SymbolFilters,
    TradeIntent,
    decision_payload,
)
from tests.risk_helpers import (
    FILTERS,
    NOW,
    D,
    make_engine,
    make_intent,
    make_market,
    make_portfolio,
    position,
)


def decide(
    intent: TradeIntent | None = None,
    portfolio: PortfolioState | None = None,
    market: MarketState | None = None,
    engine: RiskEngine | None = None,
    filters: SymbolFilters = FILTERS,
    **kw: Any,
) -> RiskDecision:
    engine = engine or make_engine()
    return engine.evaluate(
        intent or make_intent(),
        portfolio or make_portfolio(),
        market or make_market(),
        filters,
        **kw,
    )


def test_a_clean_request_is_approved_and_sized_by_the_engine() -> None:
    d = decide()
    assert d.approved and d.reasons == ()
    assert D("21.7") < d.qty < D("21.8")
    assert d.notional == d.qty * D(100) and d.risk_amount == d.qty * D(2)
    assert d.risk_amount <= D(10_000) * D("0.005")  # never more than 0.5% of equity at the stop
    assert (d.entry, d.stop, d.tp1) == (D(100), D(98), D(105))
    assert all(c.passed for c in d.checks)
    names = [c.name for c in d.checks]
    assert {"bot_running", "stop_loss", "risk_reward", "max_positions", "cash_reserve"} <= set(
        names
    )


def test_decision_is_explainable_and_json_safe() -> None:
    d = decide()
    text = d.explain()
    assert "OK  bot_running" in text and "FAIL" not in text
    payload = decision_payload(make_intent(signal_id="sig1", is_manual=True), d)
    json.dumps(payload)  # must serialise (money as strings)
    assert (
        payload["approved"] is True
        and payload["manual"] is True
        and isinstance(payload["qty"], str)
    )


def test_rejection_lists_every_failed_check_not_just_the_first() -> None:
    d = decide(
        intent=make_intent(stop=D(0)),
        market=make_market(bot_status=BotStatus.PAUSED, data_age_s=9.0, blackout=True),
    )
    assert not d.approved and d.qty == 0 and d.notional == 0
    assert {Reason.NO_STOP, Reason.BOT_NOT_RUNNING, Reason.STALE_DATA, Reason.BLACKOUT} <= set(
        d.reasons
    )
    assert "FAIL" in d.explain()


@pytest.mark.parametrize("status", [BotStatus.DRAFT, BotStatus.PAUSED, BotStatus.KILLED])
def test_only_running_or_paper_bots_may_enter(status: BotStatus) -> None:
    assert Reason.BOT_NOT_RUNNING in decide(market=make_market(bot_status=status)).reasons


def test_paper_status_is_allowed() -> None:
    assert decide(market=make_market(bot_status=BotStatus.PAPER)).approved


def test_stale_data_and_clock_drift_boundaries() -> None:
    assert decide(market=make_market(data_age_s=4.99)).approved
    assert Reason.STALE_DATA in decide(market=make_market(data_age_s=5.0)).reasons
    assert decide(market=make_market(clock_drift_ms=499)).approved
    assert Reason.CLOCK_DRIFT in decide(market=make_market(clock_drift_ms=500)).reasons


def test_every_order_needs_a_stop_on_the_correct_side_including_manual_ones() -> None:
    manual_no_stop = make_intent(stop=D(0), is_manual=True)  # no shortcuts for manual orders
    assert Reason.NO_STOP in decide(manual_no_stop).reasons
    assert Reason.BAD_STOP_SIDE in decide(make_intent(stop=D(101))).reasons
    assert Reason.BAD_STOP_SIDE in decide(make_intent(stop=D(100))).reasons


def test_risk_reward_after_costs_must_reach_1_5() -> None:
    assert decide(make_intent(tp1=D(105))).approved  # ~2.0 after costs
    # raw R:R is 1.55 (3.1 / 2) but fees + slippage push it below 1.5
    d = decide(make_intent(tp1=D("103.1")))
    assert Reason.RR_TOO_LOW in d.reasons
    assert "after costs" in next(c.detail for c in d.checks if c.name == "risk_reward")


def test_missing_or_invalid_target_is_rejected_because_rr_cannot_be_verified() -> None:
    assert Reason.NO_TARGET in decide(make_intent(tp1=None)).reasons  # e.g. trailing-only S3
    assert Reason.NO_TARGET in decide(make_intent(tp1=D(99))).reasons


def test_short_entries_are_not_supported_on_spot() -> None:
    d = decide(make_intent(side=Side.SELL))
    assert d.reasons == (Reason.SHORT_NOT_SUPPORTED,)


def test_invalid_input_and_zero_score_are_rejected_without_raising() -> None:
    assert decide(portfolio=make_portfolio(equity=0)).reasons == (Reason.INVALID_INPUT,)
    skipped = decide(make_intent(size_factor=D(0)))
    assert Reason.SCORE_SKIP in skipped.reasons and not skipped.approved
    assert decide(make_intent(entry=D("0.001"), stop=D("0.0005"))).approved is False  # rounds to 0


def test_cooldown_and_blackout() -> None:
    cooling = make_market(cooldowns={"BTCUSDT": NOW + timedelta(hours=1)})
    assert Reason.COOLDOWN in decide(market=cooling).reasons
    expired = make_market(cooldowns={"BTCUSDT": NOW - timedelta(seconds=1)})
    assert decide(market=expired).approved
    other = make_market(cooldowns={"ETHUSDT": NOW + timedelta(hours=1)})
    assert decide(market=other).approved  # cooldown is per symbol
    assert Reason.BLACKOUT in decide(market=make_market(blackout=True)).reasons


def test_market_orders_need_a_depth_based_slippage_estimate_within_30_bps() -> None:
    assert Reason.MARKET_ORDER_NO_DEPTH in decide(make_intent(order_type="MARKET")).reasons
    ok = decide(make_intent(order_type="MARKET", expected_slippage_bps=D(30)))
    assert ok.approved
    bad = decide(make_intent(order_type="MARKET", expected_slippage_bps=D(31)))
    assert Reason.SLIPPAGE in bad.reasons


def test_limit_orders_are_enforced_after_sustained_slippage() -> None:
    e = make_engine()
    for _ in range(10):
        e.breakers.record_trade_result(D(1), slippage=D("0.003"))
    d = decide(make_intent(order_type="MARKET", expected_slippage_bps=D(5)), engine=e)
    assert Reason.SLIPPAGE in d.reasons and "limit orders enforced" in d.explain()
    assert decide(make_intent(order_type="LIMIT"), engine=e).approved  # limit orders still fine


def test_no_data_ever_means_no_trade() -> None:
    from app.risk import RiskEngine, RiskProfile

    d = RiskEngine(RiskProfile()).evaluate(make_intent(), make_portfolio(), make_market(), FILTERS)
    assert Reason.BREAKER_ACTIVE in d.reasons and not d.approved


def test_daily_loss_breaker_blocks_entries_and_clears_next_day() -> None:
    e = make_engine()
    losing = make_portfolio(equity=9700, day_start=10_000, week_start=10_000, peak=10_000)
    d = decide(portfolio=losing, engine=e)
    assert Reason.BREAKER_ACTIVE in d.reasons
    tomorrow = NOW + timedelta(hours=13)
    e.breakers.record_tick(tomorrow)
    fine = make_portfolio(equity=9700, day_start=9700, week_start=10_000, peak=10_000)
    assert decide(portfolio=fine, market=make_market(now=tomorrow), engine=e).approved


def test_drawdown_kill_switch_latches_across_decisions_until_2fa_reset() -> None:
    e = make_engine()
    crashed = make_portfolio(equity=8700, peak=10_000, day_start=8700, week_start=8700)
    d = decide(portfolio=crashed, engine=e)
    assert Reason.KILL_SWITCH in d.reasons
    recovered = make_portfolio(equity=10_000, peak=10_000)
    assert Reason.KILL_SWITCH in decide(portfolio=recovered, engine=e).reasons  # still latched
    e.breakers.reset_kill(totp_verified=True)
    assert decide(portfolio=recovered, engine=e).approved


def test_losing_streak_halves_the_approved_size() -> None:
    normal = decide()
    e = make_engine()
    for _ in range(4):
        e.breakers.record_trade_result(D(-5))
    halved = decide(engine=e)
    assert halved.approved and abs(halved.qty - normal.qty / 2) < D("0.0001")
    assert any("halved" in a for a in halved.adjustments)


def test_regime_and_score_factors_shrink_the_order() -> None:
    full = decide()
    reduced = decide(make_intent(regime_factor=D("0.5"), size_factor=D("0.5")))
    assert abs(reduced.qty - full.qty / 4) < D("0.0001")


def test_prices_are_rounded_to_the_tick_and_risk_is_computed_on_the_rounded_prices() -> None:
    d = decide(make_intent(entry=D("100.019"), stop=D("97.999"), tp1=D("105.009")))
    assert (d.entry, d.stop, d.tp1) == (D("100.01"), D("97.99"), D("105.00"))
    assert d.risk_amount == d.qty * (d.entry - d.stop)


def test_exposure_limits_flow_through_the_engine() -> None:
    held = (position("BTCUSDT", 2000),)
    d = decide(portfolio=make_portfolio(positions=held))
    assert d.approved and d.qty == D("5") and d.adjustments  # reduced to the symbol cap
    full = (position("BTCUSDT", 2500),)
    assert Reason.SYMBOL_EXPOSURE in decide(portfolio=make_portfolio(positions=full)).reasons


def test_size_that_falls_under_exchange_minimums_is_skipped() -> None:
    big_min = SymbolFilters(D("0.01"), D("0.00001"), D("0.00001"), D(9000), D(5000))
    assert Reason.BELOW_MIN_NOTIONAL in decide(filters=big_min).reasons
    big_qty = SymbolFilters(D("0.01"), D("0.00001"), D(50), D(9000), D(10))
    assert Reason.BELOW_MIN_QTY in decide(filters=big_qty).reasons


def test_reduction_by_symbol_cap_can_push_the_order_under_min_notional() -> None:
    held = (position("BTCUSDT", 2495),)  # only $5 of room left
    d = decide(portfolio=make_portfolio(positions=held))
    assert not d.approved and Reason.BELOW_MIN_NOTIONAL in d.reasons


def test_kelly_ceiling_reaches_the_engine() -> None:
    d = decide(kelly=D("0.004"))  # 1/4 Kelly = 0.1% < base 0.5%
    assert d.approved and d.risk_amount < D(11)


def test_regression_limits_use_tick_rounded_prices_not_the_raw_ones() -> None:
    """Found by hypothesis: the open-risk limit was checked with the raw stop (0.49235) while
    the order used the tick-rounded, wider stop (0.4923), approving 20.08 of risk against a
    20.00 limit. Limits must be evaluated on the prices the order will actually use."""
    from app.risk import PositionView

    tick4 = SymbolFilters(D("0.0001"), D("0.00001"), D("0.00001"), D(10_000_000), D(1))
    held = (
        PositionView("BTCUSDT", D(20), D("0.5"), D("0.5"), D("0.495")),
        PositionView("ETHUSDT", D(356), D("0.5"), D("0.5"), D("0.45")),
    )
    pf = make_portfolio(equity=1000, cash=812, positions=held)
    d = decide(
        make_intent(entry=D("0.5"), stop=D("0.49235"), tp1=D("0.52"), regime_factor=D("0.5")),
        portfolio=pf,
        filters=tick4,
    )
    if d.approved:
        assert pf.open_risk + d.qty * (d.entry - d.stop) <= D(1000) * D("0.02")
    else:
        assert Reason.OPEN_RISK in d.reasons
