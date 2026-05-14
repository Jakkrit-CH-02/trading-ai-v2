package settings

import (
	"errors"
	"time"

	"github.com/shopspring/decimal"
)

// Settings is a user-scoped configuration record. Money/percent values use
// decimal.Decimal to comply with the project's no-float rule.
type Settings struct {
	UserID              string
	DefaultSymbol       string
	DefaultTimeframe    string
	DefaultMode         string
	MaxPositionPct      decimal.Decimal
	MaxDailyDrawdownPct decimal.Decimal
	MaxSlippageBps      int
	NotifyEmail         bool
	NotifyWebhookURL    string
	UpdatedAt           time.Time
}

// Default returns the baseline settings for a freshly-provisioned user.
func Default(userID string) Settings {
	return Settings{
		UserID:              userID,
		DefaultSymbol:       "BTCUSDT",
		DefaultTimeframe:    "1m",
		DefaultMode:         "paper",
		MaxPositionPct:      decimal.NewFromFloat(0.02),
		MaxDailyDrawdownPct: decimal.NewFromFloat(0.05),
		MaxSlippageBps:      30,
		NotifyEmail:         false,
		NotifyWebhookURL:    "",
	}
}

var (
	ErrNotFound          = errors.New("settings: not found")
	ErrValidation        = errors.New("settings: validation failed")
	ErrForbidden         = errors.New("settings: forbidden")
	ErrUnauthenticated   = errors.New("settings: unauthenticated")
)
