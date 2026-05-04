package risk

import (
	"github.com/shopspring/decimal"

	"github.com/jakkrit-ch/trading-ai-v2/backend/internal/platform/config"
)

// Policy is the immutable, validated set of risk thresholds the engine enforces.
// Construct via PolicyFromConfig and pass by value to NewEngine.
type Policy struct {
	MaxPositionPct      decimal.Decimal
	MaxDailyDrawdownPct decimal.Decimal
	MaxSlippageBps      int
	RequireStopLoss     bool
}

// PolicyFromConfig converts the YAML/env-loaded RiskConfig into a Policy.
func PolicyFromConfig(c config.RiskConfig) Policy {
	return Policy{
		MaxPositionPct:      c.MaxPositionPct,
		MaxDailyDrawdownPct: c.MaxDailyDrawdownPct,
		MaxSlippageBps:      c.MaxSlippageBps,
		RequireStopLoss:     c.RequireStopLoss,
	}
}
