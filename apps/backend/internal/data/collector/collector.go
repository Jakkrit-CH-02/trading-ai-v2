// Package collector subscribes to a kline stream, writes the latest bar to
// a fast cache on every tick, and batches closed bars to durable storage.
package collector

import (
	"context"
	"log/slog"
	"time"

	"github.com/jakkrit-ch/trading-ai-v2/backend/internal/data"
	"github.com/jakkrit-ch/trading-ai-v2/backend/internal/domain"
)

// Options tunes batching behavior.
type Options struct {
	// BatchSize triggers a flush once buffered bars hit this count.
	BatchSize int
	// FlushInterval triggers a periodic flush even if BatchSize is not reached.
	FlushInterval time.Duration
	// Logger is optional.
	Logger *slog.Logger
}

func (o *Options) defaults() {
	if o.BatchSize <= 0 {
		o.BatchSize = 50
	}
	if o.FlushInterval <= 0 {
		o.FlushInterval = 2 * time.Second
	}
	if o.Logger == nil {
		o.Logger = slog.Default()
	}
}

// Collector consumes domain.Bar values and persists them.
type Collector struct {
	cache data.Cache
	repo  data.Repo
	opts  Options
}

// New constructs a Collector. cache must be non-nil; repo may be nil to disable
// durable storage (useful for read-only / cache-only deployments).
func New(cache data.Cache, repo data.Repo, opts Options) *Collector {
	opts.defaults()
	return &Collector{cache: cache, repo: repo, opts: opts}
}

// Run blocks reading bars from `in` until the channel closes or ctx is canceled.
// Returns nil on clean source-channel close, ctx.Err() on cancel.
//
// On every received bar the latest snapshot is written to the cache; bars are
// also buffered and batch-inserted to the repo on size or interval triggers.
func (c *Collector) Run(ctx context.Context, in <-chan domain.Bar) error {
	buf := make([]domain.Bar, 0, c.opts.BatchSize)
	ticker := time.NewTicker(c.opts.FlushInterval)
	defer ticker.Stop()

	flush := func(ctx context.Context) {
		if len(buf) == 0 || c.repo == nil {
			buf = buf[:0]
			return
		}
		if err := c.repo.InsertBars(ctx, buf); err != nil {
			c.opts.Logger.ErrorContext(ctx, "collector: flush failed",
				"service", "data.collector",
				"count", len(buf),
				"err", err.Error(),
			)
		}
		buf = buf[:0]
	}

	for {
		select {
		case <-ctx.Done():
			// Best-effort final flush with a fresh, short-lived context so we
			// don't drop in-flight bars when the parent is already canceled.
			fctx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
			flush(fctx)
			cancel()
			return ctx.Err()

		case bar, ok := <-in:
			if !ok {
				flush(ctx)
				return nil
			}
			if err := c.cache.SetLatestBar(ctx, bar); err != nil {
				c.opts.Logger.WarnContext(ctx, "collector: cache write failed",
					"service", "data.collector",
					"symbol", string(bar.Symbol),
					"interval", bar.Interval,
					"err", err.Error(),
				)
			}
			buf = append(buf, bar)
			if len(buf) >= c.opts.BatchSize {
				flush(ctx)
			}

		case <-ticker.C:
			flush(ctx)
		}
	}
}
