package alert

import (
	"errors"
	"net/http"

	"github.com/go-chi/chi/v5"
)

// Writer is the JSON envelope writer plugged in by the api package.
type Writer interface {
	WriteJSON(w http.ResponseWriter, status int, data interface{})
	WriteError(w http.ResponseWriter, status int, code, msg string)
}

// Handler exposes alert HTTP endpoints.
type Handler struct {
	svc *Service
	wr  Writer
}

func NewHandler(svc *Service, wr Writer) *Handler { return &Handler{svc: svc, wr: wr} }

type dto struct {
	ID        string `json:"id"`
	Type      string `json:"type"`
	Severity  string `json:"severity"`
	Message   string `json:"message"`
	Entity    string `json:"entity"`
	Read      bool   `json:"read"`
	CreatedAt int64  `json:"created_at"`
}

func toDTO(a Alert) dto {
	return dto{
		ID:        a.ID,
		Type:      string(a.Type),
		Severity:  string(a.Severity),
		Message:   a.Message,
		Entity:    a.Entity,
		Read:      a.Read,
		CreatedAt: a.CreatedAt.UnixMilli(),
	}
}

// List handles GET /api/alerts
func (h *Handler) List(w http.ResponseWriter, r *http.Request) {
	items, err := h.svc.List(r.Context(), 200)
	if err != nil {
		h.wr.WriteError(w, http.StatusInternalServerError, "internal", "list alerts failed")
		return
	}
	out := make([]dto, 0, len(items))
	for _, a := range items {
		out = append(out, toDTO(a))
	}
	h.wr.WriteJSON(w, http.StatusOK, out)
}

// Ack handles POST /api/alerts/{id}/ack
func (h *Handler) Ack(w http.ResponseWriter, r *http.Request) {
	id := chi.URLParam(r, "id")
	if id == "" {
		h.wr.WriteError(w, http.StatusBadRequest, "validation_failed", "id required")
		return
	}
	if err := h.svc.Ack(r.Context(), id); err != nil {
		switch {
		case errors.Is(err, ErrNotFound):
			h.wr.WriteError(w, http.StatusNotFound, "not_found", "alert not found")
		case errors.Is(err, ErrValidation):
			h.wr.WriteError(w, http.StatusBadRequest, "validation_failed", err.Error())
		default:
			h.wr.WriteError(w, http.StatusInternalServerError, "internal", "ack failed")
		}
		return
	}
	h.wr.WriteJSON(w, http.StatusOK, map[string]string{"id": id, "status": "acked"})
}
