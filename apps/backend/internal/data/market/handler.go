package market

import (
	"errors"
	"net/http"
	"strconv"
	"strings"

	"github.com/go-chi/chi/v5"

	"github.com/jakkrit-ch/trading-ai-v2/backend/internal/api"
	"github.com/jakkrit-ch/trading-ai-v2/backend/internal/data"
	"github.com/jakkrit-ch/trading-ai-v2/backend/internal/domain"
)

const (
	defaultInterval = "1m"
	defaultLimit    = 100
	maxLimit        = 1000
)

// Handler hosts the chi routes for market data reads.
type Handler struct{ svc *Service }

// NewHandler wires the service to a handler.
func NewHandler(svc *Service) *Handler { return &Handler{svc: svc} }

// Mount registers /api/market/* routes onto r.
func (h *Handler) Mount(r chi.Router) {
	r.Route("/api/market", func(r chi.Router) {
		r.Get("/symbols", h.handleSymbols)
		r.Get("/candles", h.handleCandles)
		r.Get("/snapshot", h.handleSnapshot)
	})
}

// SymbolsResponse is the wire DTO for GET /api/market/symbols.
type SymbolsResponse struct {
	Symbols []string `json:"symbols"`
}

func (h *Handler) handleSymbols(w http.ResponseWriter, _ *http.Request) {
	syms := h.svc.Symbols()
	out := make([]string, 0, len(syms))
	for _, s := range syms {
		out = append(out, string(s))
	}
	api.WriteJSON(w, http.StatusOK, SymbolsResponse{Symbols: out})
}

// BarDTO mirrors domain.Bar but renders decimals as strings — already the
// JSON tag default, but the explicit DTO insulates the wire from internal types.
type BarDTO struct {
	Symbol    string `json:"symbol"`
	Interval  string `json:"interval"`
	OpenTime  int64  `json:"open_time"`
	CloseTime int64  `json:"close_time"`
	Open      string `json:"open"`
	High      string `json:"high"`
	Low       string `json:"low"`
	Close     string `json:"close"`
	Volume    string `json:"volume"`
}

func toBarDTO(b domain.Bar) BarDTO {
	return BarDTO{
		Symbol:    string(b.Symbol),
		Interval:  b.Interval,
		OpenTime:  b.OpenTime,
		CloseTime: b.CloseTime,
		Open:      b.Open.String(),
		High:      b.High.String(),
		Low:       b.Low.String(),
		Close:     b.Close.String(),
		Volume:    b.Volume.String(),
	}
}

// CandlesResponse is the wire DTO for GET /api/market/candles.
type CandlesResponse struct {
	Symbol   string   `json:"symbol"`
	Interval string   `json:"interval"`
	Bars     []BarDTO `json:"bars"`
}

func (h *Handler) handleCandles(w http.ResponseWriter, r *http.Request) {
	sym, interval, ok := readSymbolInterval(w, r)
	if !ok {
		return
	}
	limit := defaultLimit
	if v := strings.TrimSpace(r.URL.Query().Get("limit")); v != "" {
		n, err := strconv.Atoi(v)
		if err != nil || n <= 0 {
			api.WriteError(w, http.StatusBadRequest, "validation_failed", "limit must be a positive integer")
			return
		}
		if n > maxLimit {
			n = maxLimit
		}
		limit = n
	}

	bars, err := h.svc.Candles(r.Context(), sym, interval, limit)
	if err != nil {
		api.WriteError(w, http.StatusInternalServerError, "internal", err.Error())
		return
	}
	out := make([]BarDTO, 0, len(bars))
	for _, b := range bars {
		out = append(out, toBarDTO(b))
	}
	api.WriteJSON(w, http.StatusOK, CandlesResponse{
		Symbol:   string(sym),
		Interval: interval,
		Bars:     out,
	})
}

// SnapshotResponse is the wire DTO for GET /api/market/snapshot.
type SnapshotResponse struct {
	Symbol   string `json:"symbol"`
	Interval string `json:"interval"`
	Latest   BarDTO `json:"latest"`
	Source   string `json:"source"` // "cache" | "repo"
}

func (h *Handler) handleSnapshot(w http.ResponseWriter, r *http.Request) {
	sym, interval, ok := readSymbolInterval(w, r)
	if !ok {
		return
	}
	bar, err := h.svc.Snapshot(r.Context(), sym, interval)
	if err != nil {
		if errors.Is(err, data.ErrNotFound) {
			api.WriteError(w, http.StatusNotFound, "not_found", "no snapshot for symbol/interval")
			return
		}
		api.WriteError(w, http.StatusInternalServerError, "internal", err.Error())
		return
	}
	// Source detection: re-probe cache only to label the response.
	source := "repo"
	if h.svc.cache != nil {
		if _, cErr := h.svc.cache.GetLatestBar(r.Context(), sym, interval); cErr == nil {
			source = "cache"
		}
	}
	api.WriteJSON(w, http.StatusOK, SnapshotResponse{
		Symbol:   string(sym),
		Interval: interval,
		Latest:   toBarDTO(bar),
		Source:   source,
	})
}

func readSymbolInterval(w http.ResponseWriter, r *http.Request) (domain.Symbol, string, bool) {
	sym := strings.ToUpper(strings.TrimSpace(r.URL.Query().Get("symbol")))
	if sym == "" {
		api.WriteError(w, http.StatusBadRequest, "validation_failed", "symbol is required")
		return "", "", false
	}
	interval := strings.TrimSpace(r.URL.Query().Get("interval"))
	if interval == "" {
		interval = defaultInterval
	}
	return domain.Symbol(sym), interval, true
}
