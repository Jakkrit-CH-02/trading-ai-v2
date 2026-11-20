"""S1 Trend Pullback (SPEC 2.2): enter on 1H, direction filtered by the 4H regime."""

from decimal import Decimal

from app.core.models import Side
from app.marketdata import indicators as ind
from app.strategies.base import (
    MarketFrames,
    base_columns,
    is_nan,
    regime_columns,
    s_tech_score,
    to_features,
)
from app.strategies.features import Features, dec
from app.strategies.params import S1Params
from app.strategies.types import Regime, Signal, TrailSpec


class S1Trend:
    name = "s1"
    exec_interval = "1h"

    def __init__(self, params: S1Params | None = None) -> None:
        self.p = params or S1Params()

    def prepare(self, data: MarketFrames) -> Features:
        p, df = self.p, data.frames["1h"]
        close, high, low = df["close"], df["high"], df["low"]
        ema_f, ema_s = ind.ema(close, p.ema_fast), ind.ema(close, p.ema_slow)
        touched = ((low <= ema_f) | (low <= ema_s)).astype(float)
        cols = base_columns(df, "1h")
        cols.update(
            ema_fast=ema_f,
            ema_slow=ema_s,
            rsi=ind.rsi(close, p.rsi_period),
            atr=ind.atr(high, low, close, p.atr_period),
            swing_low=low.rolling(p.swing_lookback, min_periods=p.swing_lookback).min(),
            touched=touched.rolling(p.pullback_lookback, min_periods=1).max(),
            vol_z=ind.volume_zscore(df["volume"], 20),
        )
        cols.update(regime_columns(data, df.index, "1h", p.regime))
        return to_features(data.symbol, "1h", cols)

    def evaluate(self, f: Features, i: int) -> Signal | None:
        p = self.p
        if i < 1:
            return None
        if f["regime4"][i] not in p.regimes or f["btc_regime"][i] == Regime.TREND_DOWN:
            return None
        close, ema_f = f["close"][i], f["ema_fast"][i]
        rsi, rsi_prev, atr, swing = f["rsi"][i], f["rsi"][i - 1], f["atr"][i], f["swing_low"][i]
        if is_nan(close, ema_f, rsi, rsi_prev, atr, swing):
            return None
        if not f["touched"][i]:  # price must have pulled back to EMA20/EMA50 recently
            return None
        if not (rsi > p.rsi_level >= rsi_prev):  # RSI turns back up through 50
            return None
        if not close > ema_f:  # closes back above EMA20
            return None
        stop = swing - p.stop_atr * atr
        if not stop < close:
            return None
        risk = close - stop
        factors = [
            f["adx4"][i] > 30,  # strong 4H trend
            f["ema_fast"][i] > f["ema_slow"][i],  # 1H alignment
            f["btc_regime"][i] == Regime.TREND_UP,  # market filter agrees
            f["vol_z"][i] > 0,  # above-average volume
        ]
        return Signal(
            strategy=self.name,
            symbol=f.symbol,
            side=Side.BUY,
            bar_time=f.time(i),
            entry=dec(close),
            stop=dec(stop),
            tp1=dec(close + p.tp1_r * risk),
            tp1_close_fraction=Decimal("0.5"),
            trail=TrailSpec(p.trail_mult, p.trail_period, after_tp1=True),
            s_tech=s_tech_score([bool(x) for x in factors]),
            reasons={
                "regime4": str(f["regime4"][i]),
                "rsi": round(float(rsi), 2),
                "swing_low": round(float(swing), 8),
                "atr": round(float(atr), 8),
                "factors": [bool(x) for x in factors],
            },
        )
