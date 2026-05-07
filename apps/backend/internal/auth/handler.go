package auth

import (
	"encoding/json"
	"errors"
	"net/http"
)

// Writer is the JSON envelope writer plugged in by the api package, so
// internal/auth has no import dependency on internal/api.
type Writer interface {
	WriteJSON(w http.ResponseWriter, status int, data interface{})
	WriteError(w http.ResponseWriter, status int, code, msg string)
}

// Handler exposes auth HTTP endpoints.
type Handler struct {
	svc *Service
	wr  Writer
}

func NewHandler(svc *Service, wr Writer) *Handler { return &Handler{svc: svc, wr: wr} }

type registerReq struct {
	Username string `json:"username"`
	Password string `json:"password"`
	Role     Role   `json:"role"`
}

type loginReq struct {
	Username string `json:"username"`
	Password string `json:"password"`
}

type loginResp struct {
	Token string     `json:"token"`
	User  PublicUser `json:"user"`
}

func (h *Handler) Register(w http.ResponseWriter, r *http.Request) {
	var req registerReq
	if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
		h.wr.WriteError(w, http.StatusBadRequest, "validation_failed", "invalid json")
		return
	}
	u, err := h.svc.Register(r.Context(), req.Username, req.Password, req.Role)
	switch {
	case errors.Is(err, ErrUserExists):
		h.wr.WriteError(w, http.StatusConflict, "user_exists", "username already taken")
		return
	case errors.Is(err, ErrInvalidRole):
		h.wr.WriteError(w, http.StatusBadRequest, "validation_failed", "invalid role")
		return
	case errors.Is(err, ErrWeakPassword):
		h.wr.WriteError(w, http.StatusBadRequest, "validation_failed", "password must be >= 8 chars")
		return
	case errors.Is(err, ErrInvalidUsername):
		h.wr.WriteError(w, http.StatusBadRequest, "validation_failed", "username must be >= 3 chars")
		return
	case err != nil:
		h.wr.WriteError(w, http.StatusInternalServerError, "internal", "register failed")
		return
	}
	h.wr.WriteJSON(w, http.StatusCreated, u)
}

func (h *Handler) Login(w http.ResponseWriter, r *http.Request) {
	var req loginReq
	if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
		h.wr.WriteError(w, http.StatusBadRequest, "validation_failed", "invalid json")
		return
	}
	tok, u, err := h.svc.Login(r.Context(), req.Username, req.Password)
	if err != nil {
		if errors.Is(err, ErrInvalidCreds) {
			h.wr.WriteError(w, http.StatusUnauthorized, "invalid_credentials", "invalid username or password")
			return
		}
		h.wr.WriteError(w, http.StatusInternalServerError, "internal", "login failed")
		return
	}
	h.wr.WriteJSON(w, http.StatusOK, loginResp{Token: tok, User: u})
}

func (h *Handler) Logout(w http.ResponseWriter, _ *http.Request) {
	// Stateless JWT: client drops the token. Endpoint exists for symmetry
	// and audit hooks.
	h.wr.WriteJSON(w, http.StatusOK, map[string]bool{"ok": true})
}

func (h *Handler) Me(w http.ResponseWriter, r *http.Request) {
	c, ok := ClaimsFromContext(r.Context())
	if !ok {
		h.wr.WriteError(w, http.StatusUnauthorized, "unauthorized", "no auth context")
		return
	}
	u, err := h.svc.Me(r.Context(), c.UserID)
	if err != nil {
		h.wr.WriteError(w, http.StatusNotFound, "not_found", "user not found")
		return
	}
	h.wr.WriteJSON(w, http.StatusOK, u)
}
