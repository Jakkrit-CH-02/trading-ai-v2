package order

import (
	"context"
	"fmt"
	"log/slog"

	"github.com/jakkrit-ch/trading-ai-v2/backend/internal/audit"
	"github.com/jakkrit-ch/trading-ai-v2/backend/internal/domain"
	"github.com/jakkrit-ch/trading-ai-v2/backend/internal/livegate"
)

// LiveExecutor wraps an underlying live-trading executor (the Binance
// adapter) with the four-condition livegate check and the audit-log write.
//
// Place is the only entry point that ever submits real money. Every call
// here must produce an audit_log row — success or failure. Refusal does NOT
// reach the underlying executor.
type LiveExecutor struct {
	gate     *livegate.Gate
	upstream Executor
	audit    audit.Recorder
}

// NewLiveExecutor wires the gate, the underlying executor, and the audit
// recorder. All three are required.
func NewLiveExecutor(gate *livegate.Gate, upstream Executor, rec audit.Recorder) *LiveExecutor {
	return &LiveExecutor{gate: gate, upstream: upstream, audit: rec}
}

// Place enforces the gate, records the attempt to the audit log, then
// delegates to the upstream executor. Audit rows are written for both
// allowed and refused submissions so the trail covers every attempt.
func (l *LiveExecutor) Place(ctx context.Context, o domain.Order) (domain.Order, error) {
	actor := actorFromContext(ctx)

	if err := l.gate.Allow(ctx); err != nil {
		details := fmt.Sprintf("symbol=%s qty=%s price=%s denied=%s",
			o.Symbol, o.Qty.String(), o.Price.String(), err.Error())
		if recErr := l.audit.Record(ctx, audit.ActionLiveSubmit, actor,
			string(domain.ModeLive), o.ID, details); recErr != nil {
			slog.ErrorContext(ctx, "audit record failed on gate denial",
				"service", "order",
				"mode", string(domain.ModeLive),
				"order_id", o.ID,
				"err", recErr.Error(),
			)
		}
		slog.WarnContext(ctx, "live order denied by gate",
			"service", "order",
			"mode", string(domain.ModeLive),
			"order_id", o.ID,
			"symbol", string(o.Symbol),
			"err", err.Error(),
		)
		return domain.Order{}, fmt.Errorf("order: live gate: %w", err)
	}

	if l.upstream == nil {
		return domain.Order{}, fmt.Errorf("order: live executor not configured: %w", ErrLiveDisabled)
	}

	placed, err := l.upstream.Place(ctx, o)
	if err != nil {
		details := fmt.Sprintf("symbol=%s qty=%s price=%s err=%s",
			o.Symbol, o.Qty.String(), o.Price.String(), err.Error())
		_ = l.audit.Record(ctx, audit.ActionLiveSubmit, actor,
			string(domain.ModeLive), o.ID, details)
		return domain.Order{}, fmt.Errorf("order: live place: %w", err)
	}

	details := fmt.Sprintf("symbol=%s side=%s qty=%s price=%s status=%s exchange_id=%s",
		placed.Symbol, placed.Side, placed.Qty.String(), placed.Price.String(),
		placed.Status, placed.ExchangeID)
	if recErr := l.audit.Record(ctx, audit.ActionLiveSubmit, actor,
		string(domain.ModeLive), placed.ID, details); recErr != nil {
		// Audit failure on a successful live submit is critical — surface it.
		return placed, fmt.Errorf("order: audit record live submit: %w", recErr)
	}
	return placed, nil
}

// actorContextKey is the context key used by HTTP middleware (or callers)
// to attach the username of the requester to the order ctx. Other
// packages set it via WithActor.
type actorContextKey struct{}

// WithActor attaches the actor (username) to ctx for audit logging.
func WithActor(ctx context.Context, actor string) context.Context {
	return context.WithValue(ctx, actorContextKey{}, actor)
}

func actorFromContext(ctx context.Context) string {
	v, _ := ctx.Value(actorContextKey{}).(string)
	if v == "" {
		return "system"
	}
	return v
}
