package strategy

import (
	"context"

	"github.com/jakkrit-ch/trading-ai-v2/backend/internal/domain"
)

// Signal is re-exported from domain so callers depend on the strategy package.
type Signal = domain.Signal

// Reason describes why a strategy produced a signal.
type Reason struct {
	Code   string `json:"code"`
	Detail string `json:"detail"`
}

// RuleConfig is a serialisable strategy configuration loaded from YAML.
type RuleConfig struct {
	Name    string            `mapstructure:"name"    yaml:"name"`
	Enabled bool              `mapstructure:"enabled" yaml:"enabled"`
	Symbol  string            `mapstructure:"symbol"  yaml:"symbol"`
	Params  map[string]string `mapstructure:"params"  yaml:"params"`
}

// Strategy turns a stream of bars into Signals. Implementations are stateful
// per symbol but must be safe to call serially from a single goroutine.
type Strategy interface {
	Name() string
	OnBar(ctx context.Context, bar domain.Bar) (Signal, error)
}
