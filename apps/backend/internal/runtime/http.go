package runtime

import (
	"encoding/json"
	"errors"
	"net/http"
)

// Handler exposes the bot control HTTP surface. It is mounted by the api
// package against the chi router.
type Handler struct {
	c *Controller
}

func NewHandler(c *Controller) *Handler { return &Handler{c: c} }

// Mount installs the four routes onto any chi-style router.
func (h *Handler) Mount(r interface {
	Post(pattern string, handler http.HandlerFunc)
	Get(pattern string, handler http.HandlerFunc)
}) {
	r.Post("/api/bot/start", h.Start)
	r.Post("/api/bot/stop", h.Stop)
	r.Post("/api/bot/pause", h.Pause)
	r.Get("/api/bot/status", h.Status)
}

func (h *Handler) Start(w http.ResponseWriter, r *http.Request) {
	if err := h.c.Start(r.Context()); err != nil {
		writeErr(w, err)
		return
	}
	writeOK(w, h.c.Status())
}

func (h *Handler) Stop(w http.ResponseWriter, r *http.Request) {
	if err := h.c.Stop(r.Context()); err != nil {
		writeErr(w, err)
		return
	}
	writeOK(w, h.c.Status())
}

func (h *Handler) Pause(w http.ResponseWriter, r *http.Request) {
	if err := h.c.Pause(r.Context()); err != nil {
		writeErr(w, err)
		return
	}
	writeOK(w, h.c.Status())
}

func (h *Handler) Status(w http.ResponseWriter, _ *http.Request) {
	writeOK(w, h.c.Status())
}

type envelope struct {
	Data  interface{} `json:"data"`
	Error *apiError   `json:"error"`
}

type apiError struct {
	Code    string `json:"code"`
	Message string `json:"message"`
}

func writeOK(w http.ResponseWriter, data interface{}) {
	w.Header().Set("Content-Type", "application/json; charset=utf-8")
	w.WriteHeader(http.StatusOK)
	_ = json.NewEncoder(w).Encode(envelope{Data: data})
}

func writeErr(w http.ResponseWriter, err error) {
	code := "internal"
	status := http.StatusInternalServerError
	switch {
	case errors.Is(err, ErrInvalidTransition),
		errors.Is(err, ErrAlreadyRunning),
		errors.Is(err, ErrNotRunning):
		code = "validation_failed"
		status = http.StatusConflict
	case errors.Is(err, ErrHalted):
		code = "forbidden"
		status = http.StatusForbidden
	}
	w.Header().Set("Content-Type", "application/json; charset=utf-8")
	w.WriteHeader(status)
	_ = json.NewEncoder(w).Encode(envelope{Error: &apiError{Code: code, Message: err.Error()}})
}
