package settings

import (
	"encoding/json"
	"errors"
	"net/http"

	"github.com/shopspring/decimal"

	"github.com/jakkrit-ch/trading-ai-v2/backend/internal/auth"
)

// Writer is the JSON envelope writer plugged in by the api package.
type Writer interface {
	WriteJSON(w http.ResponseWriter, status int, data interface{})
	WriteError(w http.ResponseWriter, status int, code, msg string)
}

// Handler exposes settings HTTP endpoints.
type Handler struct {
	svc *Service
	wr  Writer
}

func NewHandler(svc *Service, wr Writer) *Handler { return &Handler{svc: svc, wr: wr} }

// dto is the wire representation. Decimals are sent as strings per project rule.
type dto struct {
	UserID              string `json:"user_id"`
	DefaultSymbol       string `json:"default_symbol"`
	DefaultTimeframe    string `json:"default_timeframe"`
	MaxPositionPct      string `json:"max_position_pct"`
	MaxDailyDrawdownPct string `json:"max_daily_drawdown_pct"`
	MaxSlippageBps      int    `json:"max_slippage_bps"`
	NotifyEmail         bool   `json:"notify_email"`
	NotifyWebhookURL    string `json:"notify_webhook_url"`
	UpdatedAt           int64  `json:"updated_at"`
}

func toDTO(s Settings) dto {
	return dto{
		UserID:              s.UserID,
		DefaultSymbol:       s.DefaultSymbol,
		DefaultTimeframe:    s.DefaultTimeframe,
		MaxPositionPct:      s.MaxPositionPct.String(),
		MaxDailyDrawdownPct: s.MaxDailyDrawdownPct.String(),
		MaxSlippageBps:      s.MaxSlippageBps,
		NotifyEmail:         s.NotifyEmail,
		NotifyWebhookURL:    s.NotifyWebhookURL,
		UpdatedAt:           s.UpdatedAt.UnixMilli(),
	}
}

func fromDTO(d dto) (Settings, error) {
	pos, err := decimal.NewFromString(d.MaxPositionPct)
	if err != nil {
		return Settings{}, err
	}
	dd, err := decimal.NewFromString(d.MaxDailyDrawdownPct)
	if err != nil {
		return Settings{}, err
	}
	return Settings{
		DefaultSymbol:       d.DefaultSymbol,
		DefaultTimeframe:    d.DefaultTimeframe,
		MaxPositionPct:      pos,
		MaxDailyDrawdownPct: dd,
		MaxSlippageBps:      d.MaxSlippageBps,
		NotifyEmail:         d.NotifyEmail,
		NotifyWebhookURL:    d.NotifyWebhookURL,
	}, nil
}

// Get handles GET /api/settings[?user_id=...]
func (h *Handler) Get(w http.ResponseWriter, r *http.Request) {
	claims, ok := auth.ClaimsFromContext(r.Context())
	if !ok {
		h.wr.WriteError(w, http.StatusUnauthorized, "unauthorized", "no auth context")
		return
	}
	target := r.URL.Query().Get("user_id")
	s, err := h.svc.Get(r.Context(), claims, target)
	if err != nil {
		h.writeServiceErr(w, err)
		return
	}
	h.wr.WriteJSON(w, http.StatusOK, toDTO(s))
}

// Put handles PUT /api/settings[?user_id=...]
func (h *Handler) Put(w http.ResponseWriter, r *http.Request) {
	claims, ok := auth.ClaimsFromContext(r.Context())
	if !ok {
		h.wr.WriteError(w, http.StatusUnauthorized, "unauthorized", "no auth context")
		return
	}
	var d dto
	if err := json.NewDecoder(r.Body).Decode(&d); err != nil {
		h.wr.WriteError(w, http.StatusBadRequest, "validation_failed", "invalid json")
		return
	}
	in, err := fromDTO(d)
	if err != nil {
		h.wr.WriteError(w, http.StatusBadRequest, "validation_failed", "invalid decimal value")
		return
	}
	target := r.URL.Query().Get("user_id")
	if target == "" {
		target = d.UserID
	}
	out, err := h.svc.Update(r.Context(), claims, target, in)
	if err != nil {
		h.writeServiceErr(w, err)
		return
	}
	h.wr.WriteJSON(w, http.StatusOK, toDTO(out))
}

func (h *Handler) writeServiceErr(w http.ResponseWriter, err error) {
	switch {
	case errors.Is(err, ErrUnauthenticated):
		h.wr.WriteError(w, http.StatusUnauthorized, "unauthorized", err.Error())
	case errors.Is(err, ErrForbidden):
		h.wr.WriteError(w, http.StatusForbidden, "forbidden", "not allowed to access these settings")
	case errors.Is(err, ErrValidation):
		h.wr.WriteError(w, http.StatusBadRequest, "validation_failed", err.Error())
	case errors.Is(err, ErrNotFound):
		h.wr.WriteError(w, http.StatusNotFound, "not_found", "settings not found")
	default:
		h.wr.WriteError(w, http.StatusInternalServerError, "internal", "settings request failed")
	}
}
