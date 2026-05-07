package runtime

import (
	"encoding/json"
	"errors"
	"net/http"

	"github.com/jakkrit-ch/trading-ai-v2/backend/internal/livegate"
)

// Handler exposes the bot control HTTP surface. It is mounted by the api
// package against the chi router.
type Handler struct {
	c    *Controller
	gate *livegate.Gate // optional; required only for live mode
}

func NewHandler(c *Controller) *Handler { return &Handler{c: c} }

// WithGate wires the live gate so /api/bot/live-confirm can issue tokens.
// The HTTP layer must additionally enforce admin role on this endpoint
// (handled by the surrounding chi router group).
func (h *Handler) WithGate(g *livegate.Gate) *Handler { h.gate = g; return h }

// Mount installs the runtime routes onto any chi-style router.
func (h *Handler) Mount(r interface {
	Post(pattern string, handler http.HandlerFunc)
	Get(pattern string, handler http.HandlerFunc)
}) {
	r.Post("/api/bot/start", h.Start)
	r.Post("/api/bot/stop", h.Stop)
	r.Post("/api/bot/pause", h.Pause)
	r.Get("/api/bot/status", h.Status)
	r.Post("/api/bot/kill", h.Kill)
	r.Post("/api/bot/reset", h.Reset)
	r.Post("/api/bot/live-confirm", h.LiveConfirm)
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

// Kill engages the kill switch — accessible to any authenticated role so
// that the panic button is never gated behind a fast role lookup. The
// underlying middleware on the route is responsible for ensuring the
// caller is authenticated.
func (h *Handler) Kill(w http.ResponseWriter, r *http.Request) {
	if err := h.c.Kill(r.Context()); err != nil {
		writeErr(w, err)
		return
	}
	writeOK(w, h.c.Status())
}

// Reset clears halted → idle so the bot can be started again. The
// surrounding router group MUST gate this with an admin-only middleware.
func (h *Handler) Reset(w http.ResponseWriter, r *http.Request) {
	if err := h.c.Reset(r.Context()); err != nil {
		writeErr(w, err)
		return
	}
	writeOK(w, h.c.Status())
}

// LiveConfirmRequest is the body posted from the typed-phrase modal. The
// phrase must equal exactly "I UNDERSTAND THE RISK"; the surrounding
// router group MUST gate this endpoint with an admin-only middleware.
type LiveConfirmRequest struct {
	Phrase string `json:"phrase"`
}

// LiveConfirmResponse returns the issued single-use token. The frontend
// passes this on the next /api/bot/start call (header X-Live-Confirm-Token)
// which the controller threads into the order Manager via context.
type LiveConfirmResponse struct {
	Token string `json:"token"`
}

const liveConfirmPhrase = "I UNDERSTAND THE RISK"

func (h *Handler) LiveConfirm(w http.ResponseWriter, r *http.Request) {
	if h.gate == nil {
		writeErrCode(w, http.StatusServiceUnavailable, "live_disabled", "live gate not configured")
		return
	}
	var req LiveConfirmRequest
	if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
		writeErrCode(w, http.StatusBadRequest, "validation_failed", "invalid body")
		return
	}
	if req.Phrase != liveConfirmPhrase {
		writeErrCode(w, http.StatusBadRequest, "validation_failed", "confirmation phrase incorrect")
		return
	}
	tok := h.gate.IssueToken(r.Context())
	writeOK(w, LiveConfirmResponse{Token: tok})
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

func writeErrCode(w http.ResponseWriter, status int, code, msg string) {
	w.Header().Set("Content-Type", "application/json; charset=utf-8")
	w.WriteHeader(status)
	_ = json.NewEncoder(w).Encode(envelope{Error: &apiError{Code: code, Message: msg}})
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
