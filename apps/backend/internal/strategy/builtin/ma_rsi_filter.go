package builtin

import (
	"context"
	"fmt"

	"github.com/shopspring/decimal"

	"github.com/jakkrit-ch/trading-ai-v2/backend/internal/domain"
	"github.com/jakkrit-ch/trading-ai-v2/backend/internal/platform/ids"
	"github.com/jakkrit-ch/trading-ai-v2/backend/internal/platform/timex"
	"github.com/jakkrit-ch/trading-ai-v2/backend/internal/strategy"
)

const MARSIFilterName = "ma_rsi_filter"

// MARSIFilter emits MA crossover signals only when the RSI gate condition is met:
// BUY cross fires only when RSI < rsiBuyMax; SELL cross fires only when RSI > rsiSellMin.
type MARSIFilter struct {
	ma         *MACross
	rsiCalc    *RSI
	rsiBuyMax  decimal.Decimal
	rsiSellMin decimal.Decimal
}

func NewMARSIFilter(fast, slow, rsiPeriod int, rsiBuyMax, rsiSellMin decimal.Decimal) *MARSIFilter {
	return &MARSIFilter{
		ma:         NewMACross(fast, slow),
		rsiCalc:    NewRSI(rsiPeriod, decimal.NewFromInt(30), decimal.NewFromInt(70)), // oversold/overbought unused — gate reads CurrentRSI() directly
		rsiBuyMax:  rsiBuyMax,
		rsiSellMin: rsiSellMin,
	}
}

func (f *MARSIFilter) Name() string { return MARSIFilterName }

func (f *MARSIFilter) OnBar(ctx context.Context, b domain.Bar) (strategy.Signal, error) {
	maSig, err := f.ma.OnBar(ctx, b)
	if err != nil {
		return strategy.Signal{}, err
	}
	if _, err = f.rsiCalc.OnBar(ctx, b); err != nil {
		return strategy.Signal{}, err
	}

	hold := strategy.Signal{
		ID:        ids.New(),
		Symbol:    b.Symbol,
		Action:    domain.SignalActionHold,
		Strategy:  MARSIFilterName,
		CreatedMs: timex.NowMs(),
	}

	if maSig.Action == domain.SignalActionHold {
		hold.Reason = maSig.Reason
		return hold, nil
	}

	rsiVal, rsiReady := f.rsiCalc.CurrentRSI()
	if !rsiReady {
		hold.Reason = "warmup"
		return hold, nil
	}

	switch maSig.Action {
	case domain.SignalActionBuy:
		if rsiVal.LessThan(f.rsiBuyMax) {
			return strategy.Signal{
				ID:        ids.New(),
				Symbol:    b.Symbol,
				Action:    domain.SignalActionBuy,
				Strategy:  MARSIFilterName,
				Reason:    fmt.Sprintf("%s; rsi %s < buy_max %s", maSig.Reason, rsiVal.StringFixed(2), f.rsiBuyMax.StringFixed(2)),
				Strength:  maSig.Strength,
				CreatedMs: timex.NowMs(),
			}, nil
		}
		hold.Reason = fmt.Sprintf("rsi_gate_blocked: rsi %s >= buy_max %s", rsiVal.StringFixed(2), f.rsiBuyMax.StringFixed(2))
	case domain.SignalActionSell:
		if rsiVal.GreaterThan(f.rsiSellMin) {
			return strategy.Signal{
				ID:        ids.New(),
				Symbol:    b.Symbol,
				Action:    domain.SignalActionSell,
				Strategy:  MARSIFilterName,
				Reason:    fmt.Sprintf("%s; rsi %s > sell_min %s", maSig.Reason, rsiVal.StringFixed(2), f.rsiSellMin.StringFixed(2)),
				Strength:  maSig.Strength,
				CreatedMs: timex.NowMs(),
			}, nil
		}
		hold.Reason = fmt.Sprintf("rsi_gate_blocked: rsi %s <= sell_min %s", rsiVal.StringFixed(2), f.rsiSellMin.StringFixed(2))
	}

	return hold, nil
}

// MARSIFilterFactory builds MARSIFilter from a RuleConfig.
// Params: "fast" (default 9), "slow" (default 21), "rsi_period" (default 14),
//
//	"rsi_buy_max" (default 60), "rsi_sell_min" (default 40).
func MARSIFilterFactory(cfg strategy.RuleConfig) (strategy.Strategy, error) {
	fast, err := paramInt(cfg.Params, "fast", 9)
	if err != nil {
		return nil, err
	}
	slow, err := paramInt(cfg.Params, "slow", 21)
	if err != nil {
		return nil, err
	}
	rsiPeriod, err := paramInt(cfg.Params, "rsi_period", 14)
	if err != nil {
		return nil, err
	}
	rsiBuyMax, err := paramDecimal(cfg.Params, "rsi_buy_max", decimal.NewFromInt(60))
	if err != nil {
		return nil, err
	}
	rsiSellMin, err := paramDecimal(cfg.Params, "rsi_sell_min", decimal.NewFromInt(40))
	if err != nil {
		return nil, err
	}
	return NewMARSIFilter(fast, slow, rsiPeriod, rsiBuyMax, rsiSellMin), nil
}
