package alert

import (
	"context"
	"fmt"
	"log/slog"
	"time"

	"github.com/jakkrit-ch/trading-ai-v2/backend/internal/platform/ids"
)

// Notifier is the side-effect of an alert beyond DB persistence.
// Implementations must be non-blocking on the hot path.
type Notifier interface {
	Notify(ctx context.Context, a Alert)
}

// StdoutNotifier logs alerts via slog.
type StdoutNotifier struct{}

func (StdoutNotifier) Notify(ctx context.Context, a Alert) {
	slog.InfoContext(ctx, "alert raised",
		"service", "alert",
		"alert_id", a.ID,
		"type", string(a.Type),
		"severity", string(a.Severity),
		"entity", a.Entity,
		"message", a.Message,
	)
}

// Service owns alert creation rules and dispatch to notifiers + repo.
type Service struct {
	repo      Repo
	notifiers []Notifier
}

// NewService constructs a Service. Notifiers run in declared order.
// The repo itself is not a notifier; persistence always happens first.
func NewService(repo Repo, notifiers ...Notifier) *Service {
	return &Service{repo: repo, notifiers: notifiers}
}

// raise persists the alert and fans it out to notifiers.
func (s *Service) raise(ctx context.Context, t Type, sev Severity, entity, message string) (Alert, error) {
	a := Alert{
		ID:        ids.New(),
		Type:      t,
		Severity:  sev,
		Message:   message,
		Entity:    entity,
		Read:      false,
		CreatedAt: time.Now().UTC(),
	}
	if err := s.repo.Insert(ctx, a); err != nil {
		return Alert{}, fmt.Errorf("alert: insert: %w", err)
	}
	for _, n := range s.notifiers {
		n.Notify(ctx, a)
	}
	return a, nil
}

// DrawdownBreach raises a critical alert when daily drawdown is exceeded.
func (s *Service) DrawdownBreach(ctx context.Context, symbol, message string) (Alert, error) {
	return s.raise(ctx, TypeDrawdownBreach, SeverityCritical, symbol, message)
}

// OrderRejected raises a warning alert when an order is rejected by risk
// engine, exchange, or router.
func (s *Service) OrderRejected(ctx context.Context, orderID, message string) (Alert, error) {
	return s.raise(ctx, TypeOrderRejection, SeverityWarning, orderID, message)
}

// BinanceDisconnected raises a warning alert when the Binance feed disconnects.
func (s *Service) BinanceDisconnected(ctx context.Context, message string) (Alert, error) {
	return s.raise(ctx, TypeBinanceDisconnect, SeverityWarning, "binance", message)
}

// SlippageExceeded raises a warning alert when slippage exceeds policy.
func (s *Service) SlippageExceeded(ctx context.Context, symbol, message string) (Alert, error) {
	return s.raise(ctx, TypeSlippageExceeded, SeverityWarning, symbol, message)
}

// KillTriggered raises a critical alert when the kill switch is engaged.
func (s *Service) KillTriggered(ctx context.Context, actor, message string) (Alert, error) {
	return s.raise(ctx, TypeKillTriggered, SeverityCritical, actor, message)
}

// List returns recent alerts (newest first).
func (s *Service) List(ctx context.Context, limit int) ([]Alert, error) {
	return s.repo.List(ctx, limit)
}

// Ack marks an alert as read.
func (s *Service) Ack(ctx context.Context, id string) error {
	if id == "" {
		return fmt.Errorf("%w: id required", ErrValidation)
	}
	return s.repo.Ack(ctx, id)
}
