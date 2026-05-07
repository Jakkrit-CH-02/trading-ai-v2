package audit

import (
	"context"
	"fmt"
	"log/slog"
	"time"

	"github.com/jakkrit-ch/trading-ai-v2/backend/internal/platform/ids"
)

// Recorder is the minimal interface consumers depend on. Both Service and
// any test double can satisfy it.
type Recorder interface {
	Record(ctx context.Context, action Action, actor, mode, entity, details string) error
}

// Service writes audit entries through a Repo. It also logs each row at
// info so the structured log retains the trail when the DB is unavailable.
type Service struct {
	repo Repo
}

func NewService(repo Repo) *Service { return &Service{repo: repo} }

// Record appends one audit entry. Failures bubble up; callers must not
// silently swallow them on the live path.
func (s *Service) Record(ctx context.Context, action Action, actor, mode, entity, details string) error {
	if action == "" {
		return fmt.Errorf("audit: action required")
	}
	e := Entry{
		ID:        ids.New(),
		Action:    action,
		Actor:     actor,
		Mode:      mode,
		Entity:    entity,
		Details:   details,
		CreatedAt: time.Now().UTC(),
	}
	if err := s.repo.Insert(ctx, e); err != nil {
		slog.ErrorContext(ctx, "audit insert failed",
			"service", "audit",
			"action", string(action),
			"actor", actor,
			"mode", mode,
			"entity", entity,
			"err", err.Error(),
		)
		return fmt.Errorf("audit: insert: %w", err)
	}
	slog.InfoContext(ctx, "audit recorded",
		"service", "audit",
		"action", string(action),
		"actor", actor,
		"mode", mode,
		"entity", entity,
		"id", e.ID,
	)
	return nil
}

// List returns the most recent entries up to limit.
func (s *Service) List(ctx context.Context, limit int) ([]Entry, error) {
	return s.repo.List(ctx, limit)
}
