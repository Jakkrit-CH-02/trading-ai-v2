package backtest

import (
	"context"
	"errors"
	"fmt"
	"strconv"
	"strings"
	"time"

	"github.com/gofiber/fiber/v2"
	"github.com/shopspring/decimal"

	"github.com/jakkrit-ch/trading-ai-v2/backend/internal/binance"
	"github.com/jakkrit-ch/trading-ai-v2/backend/internal/data"
	"github.com/jakkrit-ch/trading-ai-v2/backend/internal/domain"
	"github.com/jakkrit-ch/trading-ai-v2/backend/internal/risk"
	"github.com/jakkrit-ch/trading-ai-v2/backend/internal/strategy"
)

const (
	defaultBacktestLimit = 1000
	maxKlinesPageLimit   = 1000
	maxAutoRangeBars     = 10000
)

// BarSource is the read-side dependency the handler uses to fetch history.
// internal/data.Repo satisfies it.
type BarSource interface {
	GetBars(ctx context.Context, sym domain.Symbol, interval string, limit int) ([]domain.Bar, error)
}

// KlineFetcher pulls historical klines from a remote source such as Binance.
type KlineFetcher interface {
	GetKlines(ctx context.Context, q binance.KlinesQuery) ([]domain.Bar, error)
}

// Handler wires backtest endpoints onto a Fiber router.
type Handler struct {
	store    Store
	bars     BarSource
	remote   KlineFetcher
	registry *strategy.Registry
	risk     *risk.Engine
}

func NewHandler(store Store, bars BarSource, reg *strategy.Registry, r *risk.Engine) *Handler {
	return &Handler{store: store, bars: bars, registry: reg, risk: r}
}

func (h *Handler) WithRemoteFetcher(f KlineFetcher) *Handler {
	h.remote = f
	return h
}

// RunRequest is the wire DTO for POST /api/backtest/run.
type RunRequest struct {
	Symbol           string            `json:"symbol"`
	Interval         string            `json:"interval"`
	StrategyName     string            `json:"strategy_name"`
	StrategyParams   map[string]string `json:"strategy_params"`
	InitialCash      string            `json:"initial_cash"`
	PositionFraction string            `json:"position_fraction"`
	StopLossPct      string            `json:"stop_loss_pct"`
	FromMs           int64             `json:"from_ms"`
	ToMs             int64             `json:"to_ms"`
	Limit            int               `json:"limit"`
}

func (h *Handler) run(c *fiber.Ctx) error {
	var req RunRequest
	if err := c.BodyParser(&req); err != nil {
		return errResp(c, fiber.StatusBadRequest, "validation_failed", "invalid json body")
	}
	cfg, err := req.toConfig()
	if err != nil {
		return errResp(c, fiber.StatusBadRequest, "validation_failed", err.Error())
	}
	if h.bars == nil {
		return errResp(c, fiber.StatusServiceUnavailable, "internal", "bar source not configured")
	}
	if h.registry == nil {
		return errResp(c, fiber.StatusServiceUnavailable, "internal", "strategy registry not configured")
	}
	strat, err := h.registry.Build(strategy.RuleConfig{
		Name:    cfg.StrategyName,
		Enabled: true,
		Symbol:  string(cfg.Symbol),
		Params:  cfg.StrategyParams,
	})
	if err != nil {
		return errResp(c, fiber.StatusBadRequest, "validation_failed", err.Error())
	}

	limit := resolveBacktestLimit(cfg, req.Limit)
	bars, err := h.loadBars(c.UserContext(), cfg, limit)
	if err != nil {
		return errResp(c, fiber.StatusInternalServerError, "internal", err.Error())
	}
	if len(bars) == 0 {
		return errResp(c, fiber.StatusNotFound, "not_found", "no bars available for symbol/interval")
	}

	res, err := NewEngine(cfg, strat, h.risk).Run(c.UserContext(), bars)
	if err != nil {
		return errResp(c, fiber.StatusBadRequest, "validation_failed", err.Error())
	}
	if h.store != nil {
		if err := h.store.Insert(c.UserContext(), res); err != nil {
			return errResp(c, fiber.StatusInternalServerError, "internal", err.Error())
		}
	}
	return c.JSON(okEnv(res))
}

func (h *Handler) loadBars(ctx context.Context, cfg Config, limit int) ([]domain.Bar, error) {
	if (cfg.FromMs > 0 || cfg.ToMs > 0) && h.remote != nil {
		bars, err := h.fetchRemoteBars(ctx, cfg, limit)
		if err != nil {
			return nil, err
		}
		if len(bars) > 0 {
			return bars, nil
		}
	}

	bars, err := h.bars.GetBars(ctx, cfg.Symbol, cfg.Interval, limit)
	if err != nil {
		return nil, err
	}
	if len(bars) > 0 {
		return bars, nil
	}
	if h.remote == nil {
		return nil, nil
	}
	return h.fetchRemoteBars(ctx, cfg, limit)
}

func (h *Handler) fetchRemoteBars(ctx context.Context, cfg Config, limit int) ([]domain.Bar, error) {
	q := buildKlinesQuery(cfg, limit)
	bars, err := h.getRemoteKlines(ctx, q)
	if err != nil {
		return nil, err
	}
	if len(bars) == 0 {
		return nil, nil
	}
	if repo, ok := h.bars.(data.Repo); ok {
		_ = repo.InsertBars(ctx, bars)
	}
	return bars, nil
}

func (h *Handler) getRemoteKlines(ctx context.Context, q binance.KlinesQuery) ([]domain.Bar, error) {
	if q.Limit <= 0 {
		q.Limit = defaultBacktestLimit
	}
	if q.Limit <= maxKlinesPageLimit && (q.StartMs <= 0 || q.EndMs <= 0) {
		return h.remote.GetKlines(ctx, q)
	}

	pageLimit := q.Limit
	if pageLimit > maxKlinesPageLimit {
		pageLimit = maxKlinesPageLimit
	}
	out := make([]domain.Bar, 0, q.Limit)
	nextStart := q.StartMs

	for len(out) < q.Limit {
		remaining := q.Limit - len(out)
		reqLimit := pageLimit
		if remaining < reqLimit {
			reqLimit = remaining
		}
		page, err := h.remote.GetKlines(ctx, binance.KlinesQuery{
			Symbol:   q.Symbol,
			Interval: q.Interval,
			StartMs:  nextStart,
			EndMs:    q.EndMs,
			Limit:    reqLimit,
		})
		if err != nil {
			return nil, err
		}
		if len(page) == 0 {
			break
		}
		out = append(out, page...)
		if len(page) < reqLimit {
			break
		}

		last := page[len(page)-1]
		nextStart = last.CloseTime + 1
		if q.EndMs > 0 && nextStart >= q.EndMs {
			break
		}
		if len(page) == 1 && page[0].CloseTime < nextStart {
			break
		}
	}

	return out, nil
}

func buildKlinesQuery(cfg Config, limit int) binance.KlinesQuery {
	startMs := cfg.FromMs
	endMs := cfg.ToMs
	if startMs > 0 && endMs > 0 && startMs >= endMs {
		if stepMs, ok := intervalStepMs(cfg.Interval); ok && limit > 1 {
			startMs = endMs - int64(limit-1)*stepMs
			if startMs < 0 {
				startMs = 0
			}
		} else {
			startMs = 0
		}
	}
	return binance.KlinesQuery{
		Symbol:   string(cfg.Symbol),
		Interval: cfg.Interval,
		StartMs:  startMs,
		EndMs:    endMs,
		Limit:    limit,
	}
}

func resolveBacktestLimit(cfg Config, requested int) int {
	if requested > 0 {
		return requested
	}
	stepMs, ok := intervalStepMs(cfg.Interval)
	if !ok || stepMs <= 0 {
		return defaultBacktestLimit
	}
	var spanMs int64
	switch {
	case cfg.FromMs > 0 && cfg.ToMs > cfg.FromMs:
		spanMs = cfg.ToMs - cfg.FromMs
	case cfg.FromMs > 0:
		spanMs = time.Now().UTC().UnixMilli() - cfg.FromMs
	case cfg.ToMs > 0:
		spanMs = cfg.ToMs
	default:
		return defaultBacktestLimit
	}
	if spanMs <= 0 {
		return defaultBacktestLimit
	}
	bars := int(spanMs/stepMs) + 1
	if bars < 1 {
		return defaultBacktestLimit
	}
	if bars > maxAutoRangeBars {
		return maxAutoRangeBars
	}
	return bars
}

func intervalStepMs(interval string) (int64, bool) {
	if len(interval) < 2 {
		return 0, false
	}
	n, err := strconv.Atoi(interval[:len(interval)-1])
	if err != nil || n <= 0 {
		return 0, false
	}
	var unit time.Duration
	switch interval[len(interval)-1] {
	case 'm':
		unit = time.Minute
	case 'h':
		unit = time.Hour
	case 'd':
		unit = 24 * time.Hour
	default:
		return 0, false
	}
	return int64(time.Duration(n) * unit / time.Millisecond), true
}

func (h *Handler) list(c *fiber.Ctx) error {
	if h.store == nil {
		return errResp(c, fiber.StatusServiceUnavailable, "internal", "store not configured")
	}
	limit, offset := 100, 0
	if v := strings.TrimSpace(c.Query("limit")); v != "" {
		n, err := strconv.Atoi(v)
		if err != nil || n <= 0 {
			return errResp(c, fiber.StatusBadRequest, "validation_failed", "limit must be a positive integer")
		}
		limit = n
	}
	if v := strings.TrimSpace(c.Query("offset")); v != "" {
		n, err := strconv.Atoi(v)
		if err != nil || n < 0 {
			return errResp(c, fiber.StatusBadRequest, "validation_failed", "offset must be non-negative")
		}
		offset = n
	}
	results, total, err := h.store.List(c.UserContext(), limit, offset)
	if err != nil {
		return errResp(c, fiber.StatusInternalServerError, "internal", err.Error())
	}
	return c.JSON(okEnv(struct {
		Results []Result `json:"results"`
		Total   int      `json:"total"`
		Limit   int      `json:"limit"`
		Offset  int      `json:"offset"`
	}{Results: results, Total: total, Limit: limit, Offset: offset}))
}

func (h *Handler) get(c *fiber.Ctx) error {
	if h.store == nil {
		return errResp(c, fiber.StatusServiceUnavailable, "internal", "store not configured")
	}
	id := c.Params("id")
	if id == "" {
		return errResp(c, fiber.StatusBadRequest, "validation_failed", "id required")
	}
	res, err := h.store.Get(c.UserContext(), id)
	if err != nil {
		if errors.Is(err, ErrNotFound) {
			return errResp(c, fiber.StatusNotFound, "not_found", "backtest not found")
		}
		return errResp(c, fiber.StatusInternalServerError, "internal", err.Error())
	}
	return c.JSON(okEnv(res))
}

func (req RunRequest) toConfig() (Config, error) {
	sym := strings.ToUpper(strings.TrimSpace(req.Symbol))
	if sym == "" {
		return Config{}, fmt.Errorf("symbol is required")
	}
	interval := strings.TrimSpace(req.Interval)
	if interval == "" {
		interval = "1m"
	}
	if strings.TrimSpace(req.StrategyName) == "" {
		return Config{}, fmt.Errorf("strategy_name is required")
	}
	cash, err := parseDec(req.InitialCash, decimal.NewFromInt(10_000))
	if err != nil {
		return Config{}, fmt.Errorf("initial_cash: %w", err)
	}
	if cash.LessThanOrEqual(decimal.Zero) {
		return Config{}, fmt.Errorf("initial_cash must be > 0")
	}
	frac, err := parseDec(req.PositionFraction, decimal.NewFromFloat(0.5))
	if err != nil {
		return Config{}, fmt.Errorf("position_fraction: %w", err)
	}
	stop, err := parseDec(req.StopLossPct, decimal.NewFromFloat(0.05))
	if err != nil {
		return Config{}, fmt.Errorf("stop_loss_pct: %w", err)
	}
	return Config{
		Symbol:           domain.Symbol(sym),
		Interval:         interval,
		StrategyName:     strings.TrimSpace(req.StrategyName),
		StrategyParams:   req.StrategyParams,
		InitialCash:      cash,
		PositionFraction: frac,
		StopLossPct:      stop,
		FromMs:           req.FromMs,
		ToMs:             req.ToMs,
	}, nil
}

func parseDec(s string, def decimal.Decimal) (decimal.Decimal, error) {
	s = strings.TrimSpace(s)
	if s == "" {
		return def, nil
	}
	return decimal.NewFromString(s)
}

func okEnv(data interface{}) fiber.Map {
	return fiber.Map{"data": data, "error": nil}
}

func errResp(c *fiber.Ctx, status int, code, msg string) error {
	return c.Status(status).JSON(fiber.Map{
		"data":  nil,
		"error": fiber.Map{"code": code, "message": msg},
	})
}

// Compile-time check: data.Repo satisfies BarSource.
var _ BarSource = (data.Repo)(nil)
