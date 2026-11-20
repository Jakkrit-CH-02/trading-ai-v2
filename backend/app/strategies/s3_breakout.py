"""S3 Volatility Breakout (SPEC 2.2): 4H squeeze, then close through the Donchian channel on
high volume. The channel and volume average exclude the breakout bar itself, so the bar
cannot define the level it breaks."""

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
from app.strategies.params import S3Params
from app.strategies.types import Regime, Signal, TrailSpec


class S3Breakout:
    name = "s3"
    exec_interval = "4h"

    def __init__(self, params: S3Params | None = None) -> None:
        self.p = params or S3Params()

    def prepare(self, data: MarketFrames) -> Features:
        p, df = self.p, data.frames["4h"]
        close, high, low = df["close"], df["high"], df["low"]
        width = ind.bollinger(close, p.bb_period)[3]
        upper, lower = ind.donchian(high, low, p.donchian)
        cols = base_columns(df, "4h")
        cols.update(
            bb_width_pct=ind.rolling_percentile(width, p.stat_window),
            don_upper=upper,
            don_lower=lower,
            vol_avg=df["volume"].rolling(p.vol_period, min_periods=p.vol_period).mean(),
            atr=ind.atr(high, low, close, p.atr_period),
            vol_z=ind.volume_zscore(df["volume"], p.vol_period),
        )
        cols.update(regime_columns(data, df.index, "4h", p.regime))
        return to_features(data.symbol, "4h", cols)

    def evaluate(self, f: Features, i: int) -> Signal | None:
        p = self.p
        if i < 1:
            return None
        if f["regime4"][i] not in p.regimes or f["btc_regime"][i] == Regime.TREND_DOWN:
            return None
        close, volume = f["close"][i], f["volume"][i]
        sq, up, lo, avg = (
            f["bb_width_pct"][i - 1],
            f["don_upper"][i - 1],
            f["don_lower"][i - 1],
            f["vol_avg"][i - 1],
        )
        if is_nan(close, volume, sq, up, lo, avg):
            return None
        if not sq < p.squeeze_pct:  # a squeeze existed *before* the breakout bar
            return None
        if not close > up:  # close above the prior 20-bar high
            return None
        if not volume > p.vol_mult * avg:
            return None
        stop = (up + lo) / 2  # middle of the Donchian range
        if not stop < close:
            return None
        factors = [
            sq < p.squeeze_pct / 2,  # tight squeeze
            volume > 2 * avg,
            f["btc_regime"][i] == Regime.TREND_UP,
            f["adx4"][i] > 30,
        ]
        return Signal(
            strategy=self.name,
            symbol=f.symbol,
            side=Side.BUY,
            bar_time=f.time(i),
            entry=dec(close),
            stop=dec(stop),
            trail=TrailSpec(p.trail_mult, p.atr_period, after_tp1=False),
            false_breakout=(dec(up), p.false_breakout_bars),
            s_tech=s_tech_score([bool(x) for x in factors]),
            reasons={
                "squeeze_pct": round(float(sq), 4),
                "donchian_upper": round(float(up), 8),
                "volume_ratio": round(float(volume / avg), 2),
                "factors": [bool(x) for x in factors],
            },
        )
