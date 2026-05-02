package api

import (
	"context"
	"log/slog"
	"net/http"
	"strings"
	"time"

	"github.com/go-chi/chi/v5"
	chimw "github.com/go-chi/chi/v5/middleware"

	"github.com/jakkrit-ch/trading-ai-v2/backend/internal/api/handlers"
	"github.com/jakkrit-ch/trading-ai-v2/backend/internal/platform/config"
)

// devToken is a hardcoded bearer token used until real auth lands.
const devToken = "dev"

// Pinger probes a backing dependency. Implementations must honor ctx and return
// nil on success. *pgxpool.Pool and *redis.Client both satisfy this via their
// Ping methods (with a small adapter for redis).
type Pinger interface {
	Ping(ctx context.Context) error
}

// Server wires the chi router together with its dependencies.
type Server struct {
	cfg    config.Config
	router *chi.Mux
	pg     Pinger
	rdb    Pinger
	ai     *aiClient
	aiH    *handlers.AI
}

// New constructs the HTTP server with all middleware and routes mounted.
// pg and rdb may be nil if the dependency failed to initialize at startup;
// /healthz will report them as down rather than ping.
func New(cfg config.Config, pg, rdb Pinger) *Server {
	s := &Server{
		cfg:    cfg,
		router: chi.NewRouter(),
		pg:     pg,
		rdb:    rdb,
		ai:     newAIClient(cfg.AI.BaseURL),
		aiH:    handlers.NewAI(cfg.AI.BaseURL),
	}
	s.mountMiddleware()
	s.mountRoutes()
	return s
}

// Handler returns the underlying http.Handler.
func (s *Server) Handler() http.Handler { return s.router }

// Addr returns the configured listen address.
func (s *Server) Addr() string {
	host := s.cfg.Server.Host
	if host == "" {
		host = "0.0.0.0"
	}
	return host + ":" + itoa(s.cfg.Server.Port)
}

func (s *Server) mountMiddleware() {
	s.router.Use(chimw.Recoverer)
	s.router.Use(chimw.RequestID)
	s.router.Use(slogMiddleware)
	s.router.Use(corsMiddleware)
	s.router.Use(authMiddleware)
}

func (s *Server) mountRoutes() {
	s.router.Get("/healthz", s.handleHealthz)
	s.router.Get("/api/ai/healthz", s.handleAIHealthz)
	s.router.Post("/api/ai/datasets/build", s.aiH.BuildDataset)
	s.router.Post("/api/ai/features/compute", s.aiH.ComputeFeatures)
	// /debug/error always returns the error envelope shape. Useful for
	// integration tests and frontend wiring; safe to leave mounted because
	// it carries no behavior beyond producing a deterministic error body.
	s.router.Get("/debug/error", func(w http.ResponseWriter, _ *http.Request) {
		WriteErrorWithDetails(w, http.StatusTeapot, "debug_forced_error",
			"forced error for envelope verification",
			map[string]interface{}{"reason": "debug endpoint"})
	})
}

// slogMiddleware logs every request with structured fields including request_id.
func slogMiddleware(next http.Handler) http.Handler {
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		start := time.Now()
		reqID := chimw.GetReqID(r.Context())
		ctx := context.WithValue(r.Context(), ctxKeyRequestID{}, reqID)
		ww := chimw.NewWrapResponseWriter(w, r.ProtoMajor)
		next.ServeHTTP(ww, r.WithContext(ctx))
		slog.InfoContext(ctx, "http request",
			"service", "api",
			"request_id", reqID,
			"method", r.Method,
			"path", r.URL.Path,
			"status", ww.Status(),
			"bytes", ww.BytesWritten(),
			"dur_ms", time.Since(start).Milliseconds(),
		)
	})
}

// corsMiddleware sets permissive CORS headers for dev. Real deployments will
// front the API with a reverse proxy that handles this.
func corsMiddleware(next http.Handler) http.Handler {
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		origin := r.Header.Get("Origin")
		if origin == "" {
			origin = "*"
		}
		w.Header().Set("Access-Control-Allow-Origin", origin)
		w.Header().Set("Vary", "Origin")
		w.Header().Set("Access-Control-Allow-Methods", "GET, POST, PUT, PATCH, DELETE, OPTIONS")
		w.Header().Set("Access-Control-Allow-Headers", "Authorization, Content-Type")
		if r.Method == http.MethodOptions {
			w.WriteHeader(http.StatusNoContent)
			return
		}
		next.ServeHTTP(w, r)
	})
}

// authMiddleware enforces a hardcoded `Authorization: Bearer dev` header
// on every route except /healthz. To be replaced by real auth later.
func authMiddleware(next http.Handler) http.Handler {
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.URL.Path == "/healthz" || r.URL.Path == "/api/ai/healthz" {
			next.ServeHTTP(w, r)
			return
		}
		h := r.Header.Get("Authorization")
		if !strings.EqualFold(h, "Bearer "+devToken) {
			WriteError(w, http.StatusUnauthorized, "forbidden", "missing or invalid bearer token")
			return
		}
		next.ServeHTTP(w, r)
	})
}

type ctxKeyRequestID struct{}

func itoa(n int) string {
	if n == 0 {
		return "0"
	}
	neg := n < 0
	if neg {
		n = -n
	}
	var buf [20]byte
	i := len(buf)
	for n > 0 {
		i--
		buf[i] = byte('0' + n%10)
		n /= 10
	}
	if neg {
		i--
		buf[i] = '-'
	}
	return string(buf[i:])
}
