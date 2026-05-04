package risk

import (
	"context"
	"errors"
	"testing"

	"github.com/shopspring/decimal"
	"github.com/stretchr/testify/require"

	"github.com/jakkrit-ch/trading-ai-v2/backend/internal/domain"
	"github.com/jakkrit-ch/trading-ai-v2/backend/internal/platform/config"
)

func defaultPolicy() Policy {
	return PolicyFromConfig(config.RiskConfig{
		MaxPositionPct:      decimal.NewFromFloat(0.02),
		MaxDailyDrawdownPct: decimal.NewFromFloat(0.05),
		MaxSlippageBps:      30,
		RequireStopLoss:     true,
	})
}

func okProposal() Proposal {
	return Proposal{
		Signal: domain.Signal{
			ID:     "sig_01",
			Symbol: "BTCUSDT",
			Action: domain.SignalActionBuy,
		},
		Side:        domain.SideBuy,
		OrderType:   domain.OrderTypeMarket,
		Qty:         decimal.NewFromFloat(0.001),
		Price:       decimal.NewFromInt(50000),
		StopLoss:    decimal.NewFromInt(49000),
		Equity:      decimal.NewFromInt(10000),
		DailyPnL:    decimal.Zero,
		SlippageBps: 5,
	}
}

func TestEngineValidate_Pass(t *testing.T) {
	eng := NewEngine(defaultPolicy())
	v, err := eng.Validate(context.Background(), okProposal())
	require.NoError(t, err)
	require.False(t, v.ValidatedMs == 0)
	require.Equal(t, "sig_01", v.Signal.ID)
}

func TestEngineValidate_PositionTooLarge(t *testing.T) {
	eng := NewEngine(defaultPolicy())
	p := okProposal()
	// notional = 0.01 * 50000 = 500 → 5% of 10000 equity, > 2%
	p.Qty = decimal.NewFromFloat(0.01)

	_, err := eng.Validate(context.Background(), p)
	require.Error(t, err)
	require.True(t, errors.Is(err, ErrPositionTooLarge), "want ErrPositionTooLarge, got %v", err)
}

func TestEngineValidate_DailyDrawdown(t *testing.T) {
	eng := NewEngine(defaultPolicy())
	p := okProposal()
	// loss of 600 on 10000 equity = 6%, > 5%
	p.DailyPnL = decimal.NewFromInt(-600)

	_, err := eng.Validate(context.Background(), p)
	require.Error(t, err)
	require.True(t, errors.Is(err, ErrDailyDrawdown), "want ErrDailyDrawdown, got %v", err)
}

func TestEngineValidate_StopLossRequired(t *testing.T) {
	eng := NewEngine(defaultPolicy())
	p := okProposal()
	p.StopLoss = decimal.Zero

	_, err := eng.Validate(context.Background(), p)
	require.Error(t, err)
	require.True(t, errors.Is(err, ErrStopLossRequired), "want ErrStopLossRequired, got %v", err)
}

func TestEngineValidate_SlippageExceeded(t *testing.T) {
	eng := NewEngine(defaultPolicy())
	p := okProposal()
	p.SlippageBps = 50 // > 30

	_, err := eng.Validate(context.Background(), p)
	require.Error(t, err)
	require.True(t, errors.Is(err, ErrSlippageExceeded), "want ErrSlippageExceeded, got %v", err)
}
