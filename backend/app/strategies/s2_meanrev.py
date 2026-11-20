"""S2 Mean Reversion (SPEC 2.2): RANGE regime only. Executes on 1H bars in this codebase
(the SPEC allows 15m-1H); the 4H regime still gates it."""

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
from app.strategies.params import S2Params
from app.strategies.types import Regime, Signal


class S2MeanReversion:
    name = "s2"
    exec_interval = "1h"

    def __init__(self, params: S2Params | None = None) -> None:
        self.p = params or S2Params()

    def prepare(self, data: MarketFrames) -> Features:
        p, df = self.p, data.frames["1h"]
        close, high, low = df["close"], df["high"], df["low"]
        mid, _, lower, _ = ind.bollinger(close, p.bb_period, p.bb_k)
        cols = base_columns(df, "1h")
        cols.update(
            bb_mid=mid,
            bb_lower=lower,
            rsi=ind.rsi(close, p.rsi_period),
            atr=ind.atr(high, low, close, p.atr_period),
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
        close, prev_close = f["close"][i], f["close"][i - 1]
        lower, prev_lower = f["bb_lower"][i], f["bb_lower"][i - 1]
        rsi_prev, mid, atr = f["rsi"][i - 1], f["bb_mid"][i], f["atr"][i]
        if is_nan(close, prev_close, lower, prev_lower, rsi_prev, mid, atr):
            return None
        # previous bar closed below the lower band with RSI oversold ...
        if not (prev_close < prev_lower and rsi_prev < p.rsi_oversold):
            return None
        # ... and this bar closed back inside the band
        if not close >= lower:
            return None
        if not mid > close:  # nothing to revert to
            return None
        stop = close - p.stop_atr * atr
        factors = [
            rsi_prev < p.rsi_oversold - 5,  # deeply oversold
            (prev_lower - prev_close) > 0.5 * atr,  # stretched well outside the band
            f["vol_z"][i] > 0,
            f["btc_regime"][i] in (Regime.RANGE, Regime.TREND_UP),
        ]
        return Signal(
            strategy=self.name,
            symbol=f.symbol,
            side=Side.BUY,
            bar_time=f.time(i),
            entry=dec(close),
            stop=dec(stop),
            tp1=dec(mid),
            tp1_close_fraction=Decimal(1),  # whole position exits at the middle band
            time_stop_bars=p.time_stop_bars,
            s_tech=s_tech_score([bool(x) for x in factors]),
            reasons={
                "regime4": str(f["regime4"][i]),
                "rsi_prev": round(float(rsi_prev), 2),
                "bb_mid": round(float(mid), 8),
                "atr": round(float(atr), 8),
                "factors": [bool(x) for x in factors],
            },
        )
