"""S5 Donchian trend following (research, STRATEGY_RESEARCH.md plan B): 4H close through the
previous 55-bar high while above EMA200. Long only; fixed 3xATR stop, Chandelier trail, no TP.
The channel excludes the signal bar, so the bar cannot define the level it breaks."""

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
from app.strategies.params import S5Params
from app.strategies.types import Regime, Signal, TrailSpec


class S5Donchian:
    name = "s5"
    exec_interval = "4h"

    def __init__(self, params: S5Params | None = None) -> None:
        self.p = params or S5Params()

    def prepare(self, data: MarketFrames) -> Features:
        p, df = self.p, data.frames["4h"]
        close, high, low = df["close"], df["high"], df["low"]
        upper, _ = ind.donchian(high, low, p.donchian)
        cols = base_columns(df, "4h")
        cols.update(
            don_upper=upper,
            ema50=ind.ema(close, 50),
            ema200=ind.ema(close, p.ema_trend),
            atr=ind.atr(high, low, close, p.atr_period),
            atr_trail=ind.atr(high, low, close, p.trail_period),
            vol_avg=df["volume"].rolling(p.vol_period, min_periods=p.vol_period).mean(),
        )
        cols.update(regime_columns(data, df.index, "4h", p.regime))
        return to_features(data.symbol, "4h", cols)

    def evaluate(self, f: Features, i: int) -> Signal | None:
        p = self.p
        if i < 1 or f["btc_regime"][i] == Regime.TREND_DOWN:
            return None
        close, volume, atr = f["close"][i], f["volume"][i], f["atr"][i]
        up, ema200, ema50, avg = (
            f["don_upper"][i - 1],
            f["ema200"][i],
            f["ema50"][i],
            f["vol_avg"][i - 1],
        )
        if is_nan(close, volume, atr, up, ema200, ema50, avg):
            return None
        if not (close > up and close > ema200):
            return None
        stop = close - p.stop_atr * atr
        if not 0 < stop < close:
            return None
        factors = [
            f["adx4"][i] > 25,
            f["btc_regime"][i] == Regime.TREND_UP,
            volume > 1.5 * avg,
            close > ema50 > ema200,
        ]
        return Signal(
            strategy=self.name,
            symbol=f.symbol,
            side=Side.BUY,
            bar_time=f.time(i),
            entry=dec(close),
            stop=dec(stop),
            rr_target=dec(close + p.rr_reference * (close - stop)),
            trail=TrailSpec(p.trail_mult, p.trail_period, after_tp1=False),
            s_tech=s_tech_score([bool(x) for x in factors]),
            reasons={
                "donchian_upper": round(float(up), 8),
                "atr": round(float(atr), 8),
                "factors": [bool(x) for x in factors],
            },
        )
