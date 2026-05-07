package settings

import (
	"context"
	"errors"
	"fmt"
	"strings"

	"github.com/shopspring/decimal"

	"github.com/jakkrit-ch/trading-ai-v2/backend/internal/auth"
)

// Service is the settings domain service. It owns role-based access
// enforcement and validation; the HTTP handler is a thin adapter.
type Service struct {
	repo Repo
}

func NewService(repo Repo) *Service { return &Service{repo: repo} }

// validTimeframes is the closed set accepted by Validate.
var validTimeframes = map[string]struct{}{
	"1m": {}, "3m": {}, "5m": {}, "15m": {}, "30m": {},
	"1h": {}, "2h": {}, "4h": {}, "6h": {}, "8h": {}, "12h": {},
	"1d": {}, "3d": {}, "1w": {}, "1M": {},
}

// Validate enforces invariants on a Settings record.
func Validate(s Settings) error {
	if strings.TrimSpace(s.UserID) == "" {
		return fmt.Errorf("%w: user_id required", ErrValidation)
	}
	sym := strings.ToUpper(strings.TrimSpace(s.DefaultSymbol))
	if len(sym) < 5 || len(sym) > 20 {
		return fmt.Errorf("%w: default_symbol invalid", ErrValidation)
	}
	if _, ok := validTimeframes[s.DefaultTimeframe]; !ok {
		return fmt.Errorf("%w: default_timeframe invalid", ErrValidation)
	}
	zero := decimal.Zero
	one := decimal.NewFromInt(1)
	if s.MaxPositionPct.LessThanOrEqual(zero) || s.MaxPositionPct.GreaterThan(one) {
		return fmt.Errorf("%w: max_position_pct must be in (0,1]", ErrValidation)
	}
	if s.MaxDailyDrawdownPct.LessThanOrEqual(zero) || s.MaxDailyDrawdownPct.GreaterThan(one) {
		return fmt.Errorf("%w: max_daily_drawdown_pct must be in (0,1]", ErrValidation)
	}
	if s.MaxSlippageBps < 0 || s.MaxSlippageBps > 10_000 {
		return fmt.Errorf("%w: max_slippage_bps out of range", ErrValidation)
	}
	if len(s.NotifyWebhookURL) > 2048 {
		return fmt.Errorf("%w: notify_webhook_url too long", ErrValidation)
	}
	return nil
}

// canEdit returns true iff the actor may edit settings owned by targetUserID.
// Admins may edit anyone; operators only themselves; viewers never.
func canEdit(actor *auth.Claims, targetUserID string) bool {
	if actor == nil {
		return false
	}
	switch actor.Role {
	case auth.RoleAdmin:
		return true
	case auth.RoleOperator:
		return actor.UserID == targetUserID
	}
	return false
}

// canRead returns true iff the actor may read settings for targetUserID.
// Admins may read anyone; everyone else only themselves.
func canRead(actor *auth.Claims, targetUserID string) bool {
	if actor == nil {
		return false
	}
	if actor.Role == auth.RoleAdmin {
		return true
	}
	return actor.UserID == targetUserID
}

// Get fetches settings for targetUserID, materializing defaults on first read.
// Access is gated by canRead.
func (s *Service) Get(ctx context.Context, actor *auth.Claims, targetUserID string) (Settings, error) {
	if actor == nil {
		return Settings{}, ErrUnauthenticated
	}
	if targetUserID == "" {
		targetUserID = actor.UserID
	}
	if !canRead(actor, targetUserID) {
		return Settings{}, ErrForbidden
	}
	got, err := s.repo.Get(ctx, targetUserID)
	if err != nil {
		if errors.Is(err, ErrNotFound) {
			return Default(targetUserID), nil
		}
		return Settings{}, err
	}
	return got, nil
}

// Update validates and persists settings for targetUserID. Access is gated by canEdit.
func (s *Service) Update(ctx context.Context, actor *auth.Claims, targetUserID string, in Settings) (Settings, error) {
	if actor == nil {
		return Settings{}, ErrUnauthenticated
	}
	if targetUserID == "" {
		targetUserID = actor.UserID
	}
	if !canEdit(actor, targetUserID) {
		return Settings{}, ErrForbidden
	}
	in.UserID = targetUserID
	if err := Validate(in); err != nil {
		return Settings{}, err
	}
	if err := s.repo.Upsert(ctx, in); err != nil {
		return Settings{}, fmt.Errorf("settings: upsert: %w", err)
	}
	return s.repo.Get(ctx, targetUserID)
}
