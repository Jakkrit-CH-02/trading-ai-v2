package alert

import (
	"errors"
	"time"
)

// Severity classifies the urgency of an alert.
type Severity string

const (
	SeverityInfo     Severity = "info"
	SeverityWarning  Severity = "warning"
	SeverityCritical Severity = "critical"
)

// Type identifies the rule that produced the alert.
type Type string

const (
	TypeDrawdownBreach     Type = "drawdown_breach"
	TypeOrderRejection     Type = "order_rejection"
	TypeBinanceDisconnect  Type = "binance_disconnect"
	TypeSlippageExceeded   Type = "slippage_exceeded"
	TypeKillTriggered      Type = "kill_triggered"
)

// Alert is one record in alert history.
type Alert struct {
	ID        string
	Type      Type
	Severity  Severity
	Message   string
	Entity    string // related entity ref (order id, symbol, etc.) — may be empty
	Read      bool
	CreatedAt time.Time
}

var (
	ErrNotFound   = errors.New("alert: not found")
	ErrValidation = errors.New("alert: validation failed")
)
