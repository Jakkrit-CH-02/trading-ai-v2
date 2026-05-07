package backtest

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"net/http"
	"strconv"
	"strings"

	"github.com/go-chi/chi/v5"
	"github.com/shopspring/decimal"

	"github.com/jakkrit-ch/trading-ai-v2/backend/internal/api"
	"github.com/jakkrit-ch/trading-ai-v2/backend/internal/data"
	"github.com/jakkrit-ch/trading-ai-v2/backend/internal/domain"
	"github.com/jakkrit-ch/trading-ai-v2/backend/internal/risk"
	"github.com/jakkrit-ch/trading-ai-v2/backend/internal/strategy"
)

// BarSource is the read-side dependency the handler uses to fetch history.
// internal/data.Repo satisfies it.
type BarSource interface {
	GetBars(ctx context.Context, sym domain.Symbol, interval string, limit int) ([]domain.Bar, error)
}

// Handler wires backtest endpoints onto a chi router.
type Handler struct {
	store    Store
	bars     BarSource
	registry *strategy.Registry
	risk     *risk.Engine
}

func NewHandler(store Store, bars BarSource, reg *strategy.Registry, r *risk.Engine) *Handler {
	return &Handler{store: store, bars: bars, registry: reg, risk: r}
}

// Mount registers /api/backtest/* on r.
func (h *Handler) Mount(r chi.Router) {
	r.Route("/api/backtest", func(r chi.Router) {
		r.Post("/run", h.handleRun)
		r.Get("/", h.handleList)
		r.Get("/{id}", h.handleGet)
	})
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

func (h *Handler) handleRun(w http.ResponseWriter, r *http.Request) {
	var req RunRequest
	if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
		api.WriteError(w, http.StatusBadRequest, "validation_failed", "invalid json body")
		return
	}
	cfg, err := req.toConfig()
	if err != nil {
		api.WriteError(w, http.StatusBadRequest, "validation_failed", err.Error())
		return
	}
	if h.bars == nil {
		api.WriteError(w, http.StatusServiceUnavailable, "internal", "bar source not configured")
		return
	}
	if h.registry == nil {
		api.WriteError(w, http.StatusServiceUnavailable, "internal", "strategy registry not configured")
		return
	}
	strat, err := h.registry.Build(strategy.RuleConfig{
		Name:    cfg.StrategyName,
		Enabled: true,
		Symbol:  string(cfg.Symbol),
		Params:  cfg.StrategyParams,
	})
	if err != nil {
		api.WriteError(w, http.StatusBadRequest, "validation_failed", err.Error())
		return
	}

	limit := req.Limit
	if limit <= 0 {
		limit = 1000
	}
	bars, err := h.bars.GetBars(r.Context(), cfg.Symbol, cfg.Interval, limit)
	if err != nil {
		api.WriteError(w, http.StatusInternalServerError, "internal", err.Error())
		return
	}
	if len(bars) == 0 {
		api.WriteError(w, http.StatusNotFound, "not_found", "no bars available for symbol/interval")
		return
	}

	res, err := NewEngine(cfg, strat, h.risk).Run(r.Context(), bars)
	if err != nil {
		api.WriteError(w, http.StatusBadRequest, "validation_failed", err.Error())
		return
	}
	if h.store != nil {
		if err := h.store.Insert(r.Context(), res); err != nil {
			api.WriteError(w, http.StatusInternalServerError, "internal", err.Error())
			return
		}
	}
	api.WriteJSON(w, http.StatusOK, res)
}

func (h *Handler) handleList(w http.ResponseWriter, r *http.Request) {
	if h.store == nil {
		api.WriteError(w, http.StatusServiceUnavailable, "internal", "store not configured")
		return
	}
	limit, offset := 100, 0
	if v := strings.TrimSpace(r.URL.Query().Get("limit")); v != "" {
		n, err := strconv.Atoi(v)
		if err != nil || n <= 0 {
			api.WriteError(w, http.StatusBadRequest, "validation_failed", "limit must be a positive integer")
			return
		}
		limit = n
	}
	if v := strings.TrimSpace(r.URL.Query().Get("offset")); v != "" {
		n, err := strconv.Atoi(v)
		if err != nil || n < 0 {
			api.WriteError(w, http.StatusBadRequest, "validation_failed", "offset must be non-negative")
			return
		}
		offset = n
	}
	results, total, err := h.store.List(r.Context(), limit, offset)
	if err != nil {
		api.WriteError(w, http.StatusInternalServerError, "internal", err.Error())
		return
	}
	api.WriteJSON(w, http.StatusOK, struct {
		Results []Result `json:"results"`
		Total   int      `json:"total"`
		Limit   int      `json:"limit"`
		Offset  int      `json:"offset"`
	}{Results: results, Total: total, Limit: limit, Offset: offset})
}

func (h *Handler) handleGet(w http.ResponseWriter, r *http.Request) {
	if h.store == nil {
		api.WriteError(w, http.StatusServiceUnavailable, "internal", "store not configured")
		return
	}
	id := chi.URLParam(r, "id")
	if id == "" {
		api.WriteError(w, http.StatusBadRequest, "validation_failed", "id required")
		return
	}
	res, err := h.store.Get(r.Context(), id)
	if err != nil {
		if errors.Is(err, ErrNotFound) {
			api.WriteError(w, http.StatusNotFound, "not_found", "backtest not found")
			return
		}
		api.WriteError(w, http.StatusInternalServerError, "internal", err.Error())
		return
	}
	api.WriteJSON(w, http.StatusOK, res)
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

// Compile-time check: data.Repo satisfies BarSource.
var _ BarSource = (data.Repo)(nil)
