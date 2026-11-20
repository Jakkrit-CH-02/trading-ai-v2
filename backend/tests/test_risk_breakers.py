from datetime import UTC, datetime, timedelta

import pytest

from app.risk import BreakerKind, CircuitBreakers, KillSwitchError, RiskProfile
from tests.risk_helpers import NOW, D, make_portfolio

P = RiskProfile()


def fresh(now: datetime = NOW) -> CircuitBreakers:
    b = CircuitBreakers(P)
    b.record_tick(now)
    return b


def kinds(b: CircuitBreakers, now: datetime = NOW) -> set[BreakerKind]:
    return {x.kind for x in b.active(now)}


def test_nothing_active_by_default_after_a_tick() -> None:
    b = fresh()
    assert b.active(NOW) == [] and not b.entries_blocked(NOW)
    assert b.risk_multiplier == 1 and not b.force_limit_orders and not b.kill_switch_active


def test_no_tick_ever_is_treated_as_stale_fail_safe() -> None:
    b = CircuitBreakers(P)
    assert kinds(b) == {BreakerKind.STALE_DATA} and b.entries_blocked(NOW)


# ---- loss limits ---------------------------------------------------------------------------


def test_daily_loss_pauses_until_next_utc_midnight() -> None:
    b = fresh()
    b.observe_equity(NOW, make_portfolio(equity=9790, day_start=10_000))  # -2.1%
    assert kinds(b) == {BreakerKind.DAILY_LOSS}
    assert b.entries_blocked(datetime(2025, 6, 11, 23, 59, tzinfo=UTC))
    after = datetime(2025, 6, 12, 0, 0, tzinfo=UTC)
    b.record_tick(after)
    assert not b.entries_blocked(after)


def test_loss_exactly_at_the_limit_triggers() -> None:
    b = fresh()
    b.observe_equity(NOW, make_portfolio(equity=9800, day_start=10_000))  # exactly -2%
    assert BreakerKind.DAILY_LOSS in kinds(b)
    ok = fresh()
    ok.observe_equity(NOW, make_portfolio(equity=9801, day_start=10_000))
    assert not ok.entries_blocked(NOW)


def test_weekly_loss_pauses_for_seven_days() -> None:
    b = fresh()
    b.observe_equity(NOW, make_portfolio(equity=9400, week_start=10_000, day_start=9400))
    assert kinds(b) == {BreakerKind.WEEKLY_LOSS}
    later = NOW + timedelta(days=6, hours=23)
    b.record_tick(later)
    assert b.entries_blocked(later)
    end = NOW + timedelta(days=7)
    b.record_tick(end)
    assert not b.entries_blocked(end)


def test_drawdown_from_peak_trips_a_latched_kill_switch() -> None:
    b = fresh()
    b.observe_equity(NOW, make_portfolio(equity=8800, peak=10_000, day_start=8800, week_start=8800))
    assert b.kill_switch_active and BreakerKind.KILL_SWITCH in kinds(b)
    # recovering equity does NOT clear it
    b.observe_equity(NOW, make_portfolio(equity=10_000, peak=10_000))
    assert b.kill_switch_active
    assert "drawdown" in next(x for x in b.active(NOW) if x.kind == BreakerKind.KILL_SWITCH).detail


def test_kill_switch_needs_a_verified_second_factor_to_reset() -> None:
    b = fresh()
    b.trigger_kill(NOW, "manual")
    b.trigger_kill(NOW, "second reason is ignored")
    assert next(x for x in b.active(NOW)).detail == "manual"
    with pytest.raises(KillSwitchError):
        b.reset_kill(totp_verified=False)
    assert b.kill_switch_active
    b.reset_kill(totp_verified=True)
    assert not b.kill_switch_active


# ---- loss streak ---------------------------------------------------------------------------


def test_four_losses_halve_risk_and_two_wins_restore_it() -> None:
    b = fresh()
    for _ in range(3):
        b.record_trade_result(D(-10))
    assert b.risk_multiplier == 1
    b.record_trade_result(D(-10))
    assert b.risk_multiplier == D("0.5")
    b.record_trade_result(D(5))
    assert b.risk_multiplier == D("0.5")  # one win is not enough
    b.record_trade_result(D(5))
    assert b.risk_multiplier == 1


def test_a_loss_during_recovery_restarts_the_win_count() -> None:
    b = fresh()
    for _ in range(4):
        b.record_trade_result(D(-1))
    b.record_trade_result(D(1))
    b.record_trade_result(D(-1))
    b.record_trade_result(D(1))
    assert b.risk_multiplier == D("0.5")
    b.record_trade_result(D(1))
    assert b.risk_multiplier == 1


def test_a_win_resets_the_loss_streak_and_breakeven_changes_nothing() -> None:
    b = fresh()
    for _ in range(3):
        b.record_trade_result(D(-1))
    b.record_trade_result(D(0))
    b.record_trade_result(D(1))
    b.record_trade_result(D(-1))
    assert b.risk_multiplier == 1


# ---- API errors / rate limits ----------------------------------------------------------------


def test_five_api_errors_in_a_minute_pause_entries_four_do_not() -> None:
    b = fresh()
    for i in range(4):
        b.record_api_error(NOW + timedelta(seconds=i))
    assert not b.entries_blocked(NOW + timedelta(seconds=4))
    b.record_api_error(NOW + timedelta(seconds=4))
    t = NOW + timedelta(seconds=5)
    b.record_tick(t)
    assert BreakerKind.API_ERRORS in kinds(b, t)
    later = NOW + timedelta(seconds=4 + P.api_error_pause_s)
    b.record_tick(later)
    assert not b.entries_blocked(later)


def test_old_api_errors_age_out_of_the_window() -> None:
    b = fresh()
    for i in range(4):
        b.record_api_error(NOW + timedelta(seconds=i))
    late = NOW + timedelta(seconds=120)
    b.record_api_error(late)
    b.record_tick(late)
    assert not b.entries_blocked(late)


def test_http_429_pauses_for_retry_after() -> None:
    b = fresh()
    b.record_api_error(NOW, 429, retry_after=30)
    t = NOW + timedelta(seconds=10)
    b.record_tick(t)
    assert BreakerKind.RATE_LIMIT in kinds(b, t)
    t2 = NOW + timedelta(seconds=31)
    b.record_tick(t2)
    assert not b.entries_blocked(t2)


def test_http_418_stops_immediately_and_clears_only_after_the_ban_window() -> None:
    b = fresh()
    b.record_api_error(NOW, 418, retry_after=300)
    assert BreakerKind.IP_BAN in kinds(b)
    t = NOW + timedelta(seconds=299)
    b.record_tick(t)
    assert BreakerKind.IP_BAN in kinds(b, t)
    t2 = NOW + timedelta(seconds=301)
    b.record_tick(t2)
    assert BreakerKind.IP_BAN not in kinds(b, t2)


# ---- market conditions ------------------------------------------------------------------------


def test_volatility_spike_pauses_for_an_hour() -> None:
    b = fresh()
    b.observe_market(NOW, D("0.03"), D(1))  # exactly 3% is not "more than"
    assert not b.entries_blocked(NOW)
    b.observe_market(NOW, D("-0.031"), D(1))  # falls count too
    t = NOW + timedelta(minutes=59)
    b.record_tick(t)
    assert BreakerKind.VOLATILITY in kinds(b, t)
    t2 = NOW + timedelta(minutes=60)
    b.record_tick(t2)
    assert not b.entries_blocked(t2)
    b.observe_market(t2, D("0.001"), D("3.5"))  # ATR spike alone also pauses
    assert BreakerKind.VOLATILITY in kinds(b, t2)


def test_stale_data_blocks_then_recovers_with_the_next_tick() -> None:
    b = fresh()
    stale = NOW + timedelta(seconds=11)
    assert BreakerKind.STALE_DATA in kinds(b, stale)
    b.record_tick(stale)
    assert not b.entries_blocked(stale)


def test_exchange_incident_pauses_until_a_human_clears_it() -> None:
    b = fresh()
    b.flag_exchange_event("stablecoin depeg")
    far = NOW + timedelta(days=30)
    b.record_tick(far)
    assert BreakerKind.EXCHANGE_EVENT in kinds(b, far)  # no auto-expiry
    b.clear_exchange_event()
    assert not b.entries_blocked(far)


def test_high_average_slippage_forces_limit_orders_only_with_enough_samples() -> None:
    b = fresh()
    for _ in range(9):
        b.record_trade_result(D(1), slippage=D("0.003"))
    assert not b.force_limit_orders  # 9 < min samples
    b.record_trade_result(D(1), slippage=D("0.003"))
    assert b.force_limit_orders
    for _ in range(20):  # the window keeps only the latest 20 trades
        b.record_trade_result(D(1), slippage=D("0.0005"))
    assert not b.force_limit_orders


def test_pause_is_never_shortened_by_a_weaker_repeat() -> None:
    b = fresh()
    b.record_api_error(NOW, 429, retry_after=300)
    b.record_api_error(NOW, 429, retry_after=5)
    t = NOW + timedelta(seconds=100)
    b.record_tick(t)
    assert BreakerKind.RATE_LIMIT in kinds(b, t)
