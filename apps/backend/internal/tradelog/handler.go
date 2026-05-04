package tradelog

import (
	"net/http"
	"strconv"

	"github.com/go-chi/chi/v5"

	"github.com/jakkrit-ch/trading-ai-v2/backend/internal/api"
	"github.com/jakkrit-ch/trading-ai-v2/backend/internal/domain"
	"github.com/jakkrit-ch/trading-ai-v2/backend/internal/platform/timex"
)

const (
	defaultListLimit = 100
	maxListLimit     = 1000
)

// Handler exposes the trade log over HTTP.
type Handler struct{ svc *Service }

func NewHandler(svc *Service) *Handler { return &Handler{svc: svc} }

// Mount registers /api/trades and /api/trades/summary onto r.
func (h *Handler) Mount(r chi.Router) {
	r.Route("/api/trades", func(r chi.Router) {
		r.Get("/", h.handleList)
		r.Get("/summary", h.handleSummary)
	})
}

// ListResponse is the wire DTO for GET /api/trades.
type ListResponse struct {
	Trades []Record `json:"trades"`
	Total  int      `json:"total"`
	Limit  int      `json:"limit"`
	Offset int      `json:"offset"`
}

func (h *Handler) handleList(w http.ResponseWriter, r *http.Request) {
	q := r.URL.Query()
	f := Filter{
		Mode:     domain.Mode(q.Get("mode")),
		Symbol:   domain.Symbol(q.Get("symbol")),
		Side:     domain.Side(q.Get("side")),
		Strategy: q.Get("strategy"),
	}

	if v := q.Get("from_ms"); v != "" {
		n, err := strconv.ParseInt(v, 10, 64)
		if err != nil || n < 0 {
			api.WriteError(w, http.StatusBadRequest, "validation_failed", "from_ms must be a non-negative integer")
			return
		}
		f.FromMs = n
	}
	if v := q.Get("to_ms"); v != "" {
		n, err := strconv.ParseInt(v, 10, 64)
		if err != nil || n < 0 {
			api.WriteError(w, http.StatusBadRequest, "validation_failed", "to_ms must be a non-negative integer")
			return
		}
		f.ToMs = n
	}

	limit := defaultListLimit
	if v := q.Get("limit"); v != "" {
		n, err := strconv.Atoi(v)
		if err != nil || n <= 0 {
			api.WriteError(w, http.StatusBadRequest, "validation_failed", "limit must be a positive integer")
			return
		}
		if n > maxListLimit {
			n = maxListLimit
		}
		limit = n
	}
	f.Limit = limit

	offset := 0
	if v := q.Get("offset"); v != "" {
		n, err := strconv.Atoi(v)
		if err != nil || n < 0 {
			api.WriteError(w, http.StatusBadRequest, "validation_failed", "offset must be a non-negative integer")
			return
		}
		offset = n
	}
	f.Offset = offset

	records, total, err := h.svc.List(r.Context(), f)
	if err != nil {
		api.WriteError(w, http.StatusInternalServerError, "internal", err.Error())
		return
	}
	api.WriteJSON(w, http.StatusOK, ListResponse{
		Trades: records,
		Total:  total,
		Limit:  limit,
		Offset: offset,
	})
}

func (h *Handler) handleSummary(w http.ResponseWriter, r *http.Request) {
	p := Period(r.URL.Query().Get("period"))
	switch p {
	case "":
		p = PeriodDay
	case PeriodDay, PeriodWeek, PeriodAll:
	default:
		api.WriteError(w, http.StatusBadRequest, "validation_failed", "period must be one of: day, week, all")
		return
	}

	sum, err := h.svc.Summary(r.Context(), p, timex.NowMs())
	if err != nil {
		api.WriteError(w, http.StatusInternalServerError, "internal", err.Error())
		return
	}
	api.WriteJSON(w, http.StatusOK, sum)
}
