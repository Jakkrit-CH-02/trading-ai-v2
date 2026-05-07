package api

import (
	"context"
	"log/slog"
	"net/http"
	"strings"
	"time"

	"github.com/go-chi/chi/v5"
	chimw "github.com/go-chi/chi/v5/middleware"

	"github.com/jakkrit-ch/trading-ai-v2/backend/internal/alert"
	"github.com/jakkrit-ch/trading-ai-v2/backend/internal/api/handlers"
	"github.com/jakkrit-ch/trading-ai-v2/backend/internal/auth"
	"github.com/jakkrit-ch/trading-ai-v2/backend/internal/platform/config"
	"github.com/jakkrit-ch/trading-ai-v2/backend/internal/settings"
)

// Pinger probes a backing dependency. Implementations must honor ctx and return
// nil on success. *pgxpool.Pool and *redis.Client both satisfy this via their
// Ping methods (with a small adapter for redis).
type Pinger interface {
	Ping(ctx context.Context) error
}

// Server wires the chi router together with its dependencies.
type Server struct {
	cfg     config.Config
	router  *chi.Mux
	pg      Pinger
	rdb     Pinger
	ai      *aiClient
	aiH     *handlers.AI
	authSvc *auth.Service
	authH   *auth.Handler
	settSvc *settings.Service
	settH   *settings.Handler
	alertSvc *alert.Service
	alertH   *alert.Handler
}

// Options is the optional dependency bundle for New.
type Options struct {
	Auth     *auth.Service
	Settings *settings.Service
	Alerts   *alert.Service
}

// New constructs the HTTP server with all middleware and routes mounted.
// pg and rdb may be nil if the dependency failed to initialize at startup;
// /healthz will report them as down rather than ping.
func New(cfg config.Config, pg, rdb Pinger, opts ...Options) *Server {
	var o Options
	if len(opts) > 0 {
		o = opts[0]
	}
	if o.Auth == nil {
		repo := auth.NewMemoryRepo()
		secret := cfg.Auth.JWTSecret
		if secret == "" {
			secret = "dev-secret-change-me"
		}
		o.Auth = auth.NewService(repo, auth.Config{
			JWTSecret: secret,
			JWTTTL:    time.Duration(cfg.Auth.JWTTTLSec) * time.Second,
		})
	}
	if o.Settings == nil {
		o.Settings = settings.NewService(settings.NewMemoryRepo())
	}
	if o.Alerts == nil {
		o.Alerts = alert.NewService(alert.NewMemoryRepo(), alert.StdoutNotifier{})
	}
	s := &Server{
		cfg:     cfg,
		router:  chi.NewRouter(),
		pg:      pg,
		rdb:     rdb,
		ai:      newAIClient(cfg.AI.BaseURL),
		aiH:     handlers.NewAI(cfg.AI.BaseURL),
		authSvc: o.Auth,
		authH:   auth.NewHandler(o.Auth, envelopeWriter{}),
		settSvc: o.Settings,
		settH:   settings.NewHandler(o.Settings, envelopeWriter{}),
		alertSvc: o.Alerts,
		alertH:   alert.NewHandler(o.Alerts, envelopeWriter{}),
	}
	s.mountMiddleware()
	s.mountRoutes()
	return s
}

// Handler returns the underlying http.Handler.
func (s *Server) Handler() http.Handler { return s.router }

// AuthService returns the configured auth service for external wiring/tests.
func (s *Server) AuthService() *auth.Service { return s.authSvc }

// AlertService returns the configured alert service so other subsystems
// (runtime, risk, binance connector) can raise alerts.
func (s *Server) AlertService() *alert.Service { return s.alertSvc }

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
	s.router.Use(auth.Middleware(s.authSvc, isPublicPath, writeEnvelopeError))
}

func (s *Server) mountRoutes() {
	s.router.Get("/healthz", s.handleHealthz)
	s.router.Get("/api/ai/healthz", s.handleAIHealthz)

	// Auth routes. login/register are public (see isPublicPath); me/logout
	// pass through the global JWT middleware.
	s.router.Post("/api/auth/register", s.authH.Register)
	s.router.Post("/api/auth/login", s.authH.Login)
	s.router.Post("/api/auth/logout", s.authH.Logout)
	s.router.Get("/api/auth/me", s.authH.Me)

	// Admin-only sample endpoint exercised by tests: create user as admin.
	adminMW := auth.RequireRole(writeEnvelopeError, auth.RoleAdmin)
	s.router.Group(func(r chi.Router) {
		r.Use(adminMW)
		r.Post("/api/admin/users", s.authH.Register)
	})

	// Settings: any authenticated role can read; service enforces fine-grained
	// access (admin can read/write any user; operator only self; viewer
	// read-only on self).
	s.router.Get("/api/settings", s.settH.Get)
	s.router.Put("/api/settings", s.settH.Put)

	s.router.Get("/api/alerts", s.alertH.List)
	s.router.Post("/api/alerts/{id}/ack", s.alertH.Ack)

	s.router.Post("/api/ai/datasets/build", s.aiH.BuildDataset)
	s.router.Post("/api/ai/features/compute", s.aiH.ComputeFeatures)
	s.router.Post("/api/ai/training/run", s.aiH.RunTraining)
	s.router.Get("/api/ai/training/{id}", s.aiH.GetTrainingJob)
	s.router.Get("/api/ai/models", s.aiH.ListModels)
	s.router.Post("/api/ai/models/{id}/promote", s.aiH.PromoteModel)
	s.router.Post("/api/ai/predict", s.aiH.Predict)
	s.router.Post("/api/ai/predict/reload", s.aiH.ReloadModel)

	s.router.Get("/debug/error", func(w http.ResponseWriter, _ *http.Request) {
		WriteErrorWithDetails(w, http.StatusTeapot, "debug_forced_error",
			"forced error for envelope verification",
			map[string]interface{}{"reason": "debug endpoint"})
	})
}

// isPublicPath identifies routes that bypass JWT auth.
func isPublicPath(r *http.Request) bool {
	switch r.URL.Path {
	case "/healthz",
		"/api/ai/healthz",
		"/api/auth/login",
		"/api/auth/register":
		return true
	}
	return strings.HasPrefix(r.URL.Path, "/healthz")
}

// envelopeWriter adapts package-level Write helpers to the auth.Writer interface.
type envelopeWriter struct{}

func (envelopeWriter) WriteJSON(w http.ResponseWriter, status int, data interface{}) {
	WriteJSON(w, status, data)
}

func (envelopeWriter) WriteError(w http.ResponseWriter, status int, code, msg string) {
	WriteError(w, status, code, msg)
}

func writeEnvelopeError(w http.ResponseWriter, status int, code, msg string) {
	WriteError(w, status, code, msg)
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

// corsMiddleware sets permissive CORS headers for dev.
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
