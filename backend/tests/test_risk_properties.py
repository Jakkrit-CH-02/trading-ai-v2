"""Property tests for the Risk Engine (SPEC phase 3: hypothesis).

These do not check examples; they generate hundreds of random portfolios, intents and market
states and assert that **whenever the engine approves, every risk invariant holds**, and that
it can never approve while a blocking condition is active.
"""

from dataclasses import replace
from datetime import timedelta
from decimal import Decimal

from hypothesis import HealthCheck, Phase, assume, given, settings
from hypothesis import strategies as st

from app.core.models import BotStatus, Side
from app.risk import (
    MarketState,
    PortfolioState,
    PositionView,
    Reason,
    RiskEngine,
    RiskProfile,
    SymbolFilters,
    TradeIntent,
)
from app.risk.sizing import position_size, quantize_down
from tests.risk_helpers import NOW, make_engine, make_market

D = Decimal
SETTINGS = settings(
    max_examples=400,
    deadline=None,
    suppress_health_check=[HealthCheck.too_slow, HealthCheck.filter_too_much],
)
SYMBOLS = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT", "ADAUSDT"]
PROFILE = RiskProfile()

money = st.decimals(min_value="100", max_value="2000000", places=2)
price = st.decimals(min_value="0.05", max_value="100000", places=4)
frac = st.decimals(min_value="0.001", max_value="0.6", places=4)


@st.composite
def filters(draw: st.DrawFn) -> SymbolFilters:
    tick = draw(st.sampled_from([D("0.0001"), D("0.01"), D("0.1")]))
    step = draw(st.sampled_from([D("0.00001"), D("0.001"), D("0.1"), D(1)]))
    return SymbolFilters(
        tick,
        step,
        draw(st.sampled_from([step, step * 10])),
        D(10_000_000),
        draw(st.sampled_from([D(1), D(10), D(50)])),
    )


@st.composite
def portfolios(draw: st.DrawFn) -> PortfolioState:
    equity = draw(money)
    held = draw(st.lists(st.sampled_from(SYMBOLS), max_size=5, unique=True))
    positions = []
    for sym in held:
        px = draw(price)
        notional = equity * draw(st.decimals(min_value="0.01", max_value="0.3", places=3))
        stop_gap = draw(
            st.one_of(st.none(), st.decimals(min_value="0.005", max_value="0.3", places=3))
        )
        stop = None if stop_gap is None else px * (1 - stop_gap)
        positions.append(PositionView(sym, notional / px, px, px, stop))
    invested = sum((p.notional for p in positions), D(0))
    cash = max(D(0), equity - invested)
    peak = equity * draw(st.decimals(min_value="1", max_value="1.1", places=3))
    day = equity * draw(st.decimals(min_value="0.995", max_value="1.01", places=3))
    week = equity * draw(st.decimals(min_value="0.99", max_value="1.03", places=3))
    return PortfolioState(equity, cash, peak, day, week, tuple(positions))


@st.composite
def intents(draw: st.DrawFn) -> TradeIntent:
    entry = draw(price)
    stop = entry * (1 - draw(frac))
    tp1 = entry * (1 + draw(st.decimals(min_value="0.002", max_value="0.5", places=3)))
    return TradeIntent(
        symbol=draw(st.sampled_from(SYMBOLS)),
        side=draw(st.sampled_from([Side.BUY] * 9 + [Side.SELL])),
        entry=entry,
        stop=draw(st.sampled_from([stop, stop, stop, D(0), entry * 2])),
        tp1=draw(st.sampled_from([tp1, tp1, tp1, None])),
        order_type=draw(st.sampled_from(["LIMIT", "LIMIT", "MARKET"])),
        size_factor=draw(st.sampled_from([D(1), D("0.5"), D(0)])),
        regime_factor=draw(st.sampled_from([D(1), D("0.5")])),
        expected_slippage_bps=draw(st.sampled_from([None, D(5), D(30), D(45)])),
    )


@st.composite
def markets(draw: st.DrawFn) -> MarketState:
    return make_market(
        bot_status=draw(st.sampled_from(list(BotStatus))),
        data_age_s=draw(st.sampled_from([0.1, 4.9, 5.0, 30.0])),
        clock_drift_ms=draw(st.sampled_from([10.0, 499.0, 500.0, 5000.0])),
        blackout=draw(st.booleans()),
        cooldowns=draw(
            st.sampled_from(
                [{}, {"BTCUSDT": NOW + timedelta(hours=1)}, {"ETHUSDT": NOW - timedelta(minutes=1)}]
            )
        ),
        buckets=draw(st.sampled_from([{}, {"BTCUSDT": "L1", "ETHUSDT": "L1", "SOLUSDT": "L1"}])),
    )


# ---- generators biased toward approvable requests ---------------------------------------------
# Fully random inputs are rejected ~99% of the time (bad status, stale data, no stop...), which
# would leave the approval invariants almost untested. These generate mostly-valid requests so
# the interesting limits (exposure, bucket, cash reserve, rounding) are what decides the outcome.


@st.composite
def friendly_intents(draw: st.DrawFn) -> TradeIntent:
    entry = draw(st.decimals(min_value="0.5", max_value="70000", places=4))
    gap = draw(st.decimals(min_value="0.004", max_value="0.08", places=4))
    reward = gap * draw(st.decimals(min_value="2.2", max_value="5", places=2))
    return TradeIntent(
        symbol=draw(st.sampled_from(SYMBOLS)),
        side=Side.BUY,
        entry=entry,
        stop=entry * (1 - gap),
        tp1=entry * (1 + reward),
        order_type=draw(st.sampled_from(["LIMIT"] * 4 + ["MARKET"])),
        size_factor=draw(st.sampled_from([D(1), D("0.5")])),
        regime_factor=draw(st.sampled_from([D(1), D("0.5")])),
        expected_slippage_bps=draw(st.sampled_from([D(5), D(30)])),
    )


@st.composite
def friendly_portfolios(draw: st.DrawFn) -> PortfolioState:
    equity = draw(st.decimals(min_value="1000", max_value="500000", places=2))
    held = draw(st.lists(st.sampled_from(SYMBOLS), max_size=4, unique=True))
    positions = []
    for sym in held:
        px = draw(st.decimals(min_value="0.5", max_value="70000", places=4))
        notional = equity * draw(st.decimals(min_value="0.01", max_value="0.18", places=3))
        stop = px * (1 - draw(st.decimals(min_value="0.01", max_value="0.1", places=3)))
        positions.append(PositionView(sym, notional / px, px, px, stop))
    invested = sum((p.notional for p in positions), D(0))
    return PortfolioState(
        equity, max(D(0), equity - invested), equity, equity, equity, tuple(positions)
    )


@st.composite
def friendly_markets(draw: st.DrawFn) -> MarketState:
    return make_market(
        bot_status=draw(st.sampled_from([BotStatus.RUNNING, BotStatus.PAPER])),
        data_age_s=draw(st.sampled_from([0.1, 2.0, 4.9])),
        clock_drift_ms=draw(st.sampled_from([10.0, 200.0, 499.0])),
        buckets=draw(st.sampled_from([{}, {"BTCUSDT": "L1", "ETHUSDT": "L1", "SOLUSDT": "L1"}])),
    )


# ---- sizing -------------------------------------------------------------------------------


@SETTINGS
@given(
    money,
    price,
    frac,
    st.sampled_from([D(1), D("0.5")]),
    st.sampled_from([D(1), D("0.5")]),
    filters(),
)
def test_sized_risk_never_exceeds_the_budget_and_respects_the_step(
    equity: Decimal, entry: Decimal, gap: Decimal, regime: Decimal, score: Decimal, f: SymbolFilters
) -> None:
    stop = entry * (1 - gap)
    s = position_size(equity, D("0.005"), regime, score, entry, stop, f, PROFILE)
    assert s.qty >= 0
    assert s.qty == quantize_down(s.qty, f.step_size)  # a whole number of steps
    assert s.qty * (entry - stop) <= s.risk_amount  # rounding only ever shrinks risk
    assert s.risk_amount <= equity * D("0.005")  # factors are <= 1


@SETTINGS
@given(money, price, frac, frac, filters())
def test_wider_stop_never_increases_size(
    equity: Decimal, entry: Decimal, g1: Decimal, g2: Decimal, f: SymbolFilters
) -> None:
    assume(g1 < g2)
    near = position_size(equity, D("0.005"), D(1), D(1), entry, entry * (1 - g1), f, PROFILE)
    far = position_size(equity, D("0.005"), D(1), D(1), entry, entry * (1 - g2), f, PROFILE)
    assert far.qty <= near.qty


# ---- every approval satisfies every invariant ------------------------------------------------


@SETTINGS
@given(friendly_intents(), friendly_portfolios(), friendly_markets(), filters())
def test_whenever_approved_every_risk_invariant_holds(
    intent: TradeIntent,
    pf: PortfolioState,
    market: MarketState,
    f: SymbolFilters,
) -> None:
    engine = make_engine()
    d = engine.evaluate(intent, pf, market, f)
    if not d.approved:
        assert d.qty == 0 and d.notional == 0 and d.reasons  # a rejection always says why
        return
    p, eq = PROFILE, pf.equity
    # a stop exists, is on the right side, and R:R holds after costs
    assert 0 < d.stop < d.entry
    assert d.tp1 is not None and d.tp1 > d.entry
    # sized by the engine, on exchange-legal numbers
    assert d.qty > 0 and d.qty == quantize_down(d.qty, f.step_size) and d.qty >= f.min_qty
    assert d.notional == d.qty * d.entry >= f.min_notional
    assert d.qty <= f.max_qty
    # risk at the stop: never above the hard 1% cap, nor above 0.5% x factors
    assert d.risk_amount <= eq * p.risk_per_trade_cap
    assert d.risk_amount <= eq * p.risk_per_trade * intent.regime_factor * intent.size_factor
    # exposure limits after this trade
    assert pf.symbol_notional(intent.symbol) + d.notional <= eq * p.max_symbol_exposure
    assert pf.total_exposure + d.notional <= eq * p.max_total_exposure
    new_risk = d.qty * (d.entry - d.stop)
    assert pf.open_risk + new_risk <= eq * p.max_open_risk
    bucket = market.buckets.get(intent.symbol, intent.symbol)
    assert pf.bucket_open_risk(bucket, market.buckets) + new_risk <= eq * p.max_bucket_risk
    # funds and USDT reserve
    cost = d.notional * (1 + p.fee_rate)
    assert cost <= pf.cash and pf.cash - cost >= eq * p.min_cash_reserve
    # position count
    held = {x.symbol for x in pf.positions if x.qty > 0}
    assert intent.symbol in held or len(held) < p.max_positions
    # market-order rule
    if intent.order_type == "MARKET":
        assert (
            intent.expected_slippage_bps is not None
            and intent.expected_slippage_bps <= p.max_slippage_bps
        )
    # preconditions of the checklist
    assert market.bot_status in (BotStatus.RUNNING, BotStatus.PAPER)
    assert market.data_age_s < p.max_data_age_s and market.clock_drift_ms < p.max_clock_drift_ms
    assert not market.blackout
    assert intent.symbol not in market.cooldowns or market.now >= market.cooldowns[intent.symbol]


def test_generators_actually_reach_the_approval_path() -> None:
    """Guards against a vacuous invariant test: a healthy share of generated cases must be
    approved, and the rest must be rejected for a variety of limit reasons."""
    seen = {"n": 0, "ok": 0}
    reasons: set[Reason] = set()

    @settings(
        max_examples=300,
        deadline=None,
        derandomize=True,
        phases=[Phase.generate],
        suppress_health_check=list(HealthCheck),
    )
    @given(friendly_intents(), friendly_portfolios(), friendly_markets(), filters())
    def run(i: TradeIntent, pf: PortfolioState, m: MarketState, f: SymbolFilters) -> None:
        d = make_engine().evaluate(i, pf, m, f)
        seen["n"] += 1
        seen["ok"] += d.approved
        reasons.update(d.reasons)

    run()
    assert seen["n"] >= 250
    assert seen["ok"] / seen["n"] >= 0.30, seen
    for limit in (
        Reason.SYMBOL_EXPOSURE,
        Reason.OPEN_RISK,
        Reason.MAX_POSITIONS,
        Reason.BUCKET_RISK,
    ):
        assert limit in reasons, f"{limit} is never exercised by the generators"


@SETTINGS
@given(intents(), portfolios(), markets(), filters())
def test_decisions_are_deterministic(
    intent: TradeIntent, pf: PortfolioState, market: MarketState, f: SymbolFilters
) -> None:
    a = make_engine().evaluate(intent, pf, market, f)
    b = make_engine().evaluate(intent, pf, market, f)
    assert a == b


# ---- blocking conditions can never be bypassed -------------------------------------------------


@SETTINGS
@given(
    intents(),
    portfolios(),
    filters(),
    st.sampled_from(["kill", "bot", "stale", "blackout", "stop", "no_tick"]),
)
def test_a_blocking_condition_always_prevents_approval(
    intent: TradeIntent, pf: PortfolioState, f: SymbolFilters, blocker: str
) -> None:
    engine: RiskEngine = make_engine()
    market = make_market()
    if blocker == "kill":
        engine.breakers.trigger_kill(NOW, "test")
    elif blocker == "bot":
        market = make_market(bot_status=BotStatus.KILLED)
    elif blocker == "stale":
        market = make_market(data_age_s=60.0)
    elif blocker == "blackout":
        market = make_market(blackout=True)
    elif blocker == "stop":
        intent = replace(intent, stop=D(0))  # a missing stop is never acceptable
    elif blocker == "no_tick":
        engine = RiskEngine(RiskProfile())  # never saw a price tick
    d = engine.evaluate(intent, pf, market, f)
    assert not d.approved and d.qty == 0


@SETTINGS
@given(intents(), portfolios(), markets(), filters())
def test_kill_switch_stays_latched_no_matter_what_follows(
    intent: TradeIntent,
    pf: PortfolioState,
    market: MarketState,
    f: SymbolFilters,
) -> None:
    engine = make_engine()
    engine.breakers.trigger_kill(NOW, "latched")
    for _ in range(3):
        d = engine.evaluate(intent, pf, market, f)
        assert not d.approved
    assert engine.breakers.kill_switch_active
    assert d.reasons  # always explains itself
    early = {Reason.SHORT_NOT_SUPPORTED, Reason.INVALID_INPUT, Reason.SCORE_SKIP}
    assert Reason.KILL_SWITCH in d.reasons or early & set(d.reasons)
