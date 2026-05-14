package api

import (
	"context"
	"log/slog"
	"strings"
	"time"

	"github.com/gofiber/fiber/v2"
	fibercors "github.com/gofiber/fiber/v2/middleware/cors"
	fiberlogger "github.com/gofiber/fiber/v2/middleware/logger"
	fiberrecover "github.com/gofiber/fiber/v2/middleware/recover"
	fiberrequestid "github.com/gofiber/fiber/v2/middleware/requestid"
	"github.com/jackc/pgx/v5/pgxpool"
	goredis "github.com/redis/go-redis/v9"
	"github.com/shopspring/decimal"

	aipkg "github.com/jakkrit-ch/trading-ai-v2/backend/internal/ai"
	"github.com/jakkrit-ch/trading-ai-v2/backend/internal/alert"
	"github.com/jakkrit-ch/trading-ai-v2/backend/internal/api/handlers"
	"github.com/jakkrit-ch/trading-ai-v2/backend/internal/auth"
	"github.com/jakkrit-ch/trading-ai-v2/backend/internal/backtest"
	"github.com/jakkrit-ch/trading-ai-v2/backend/internal/binance"
	"github.com/jakkrit-ch/trading-ai-v2/backend/internal/data"
	"github.com/jakkrit-ch/trading-ai-v2/backend/internal/data/market"
	"github.com/jakkrit-ch/trading-ai-v2/backend/internal/domain"
	"github.com/jakkrit-ch/trading-ai-v2/backend/internal/platform/config"
	"github.com/jakkrit-ch/trading-ai-v2/backend/internal/risk"
	"github.com/jakkrit-ch/trading-ai-v2/backend/internal/runtime"
	"github.com/jakkrit-ch/trading-ai-v2/backend/internal/settings"
	"github.com/jakkrit-ch/trading-ai-v2/backend/internal/strategy"
	"github.com/jakkrit-ch/trading-ai-v2/backend/internal/strategy/builtin"
)

// Pinger probes a backing dependency. Implementations must honor ctx and return
// nil on success. *pgxpool.Pool and *redis.Client both satisfy this via their
// Ping methods (with a small adapter for redis).
type Pinger interface {
	Ping(ctx context.Context) error
}

// Server wires the Fiber app together with its dependencies.
type Server struct {
	cfg      config.Config
	app      *fiber.App
	pg       Pinger
	rdb      Pinger
	ai       *aiClient
	authSvc  *auth.Service
	settSvc  *settings.Service
	alertSvc *alert.Service
}

// Options is the optional dependency bundle for New.
type Options struct {
	Auth     *auth.Service
	Settings *settings.Service
	Alerts   *alert.Service
}

// New constructs the Fiber HTTP server with all middleware and routes mounted.
// pg and rdb may be nil if the dependency failed to initialize at startup;
// /healthz will report them as down rather than ping.
func New(cfg config.Config, pg *pgxpool.Pool, rdb *goredis.Client, opts ...Options) *Server {
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

	mgr := runtime.NewManager(binance.Config{
		APIKey:      cfg.Binance.APIKey,
		APISecret:   cfg.Binance.APISecret,
		Testnet:     cfg.Binance.Testnet,
		RestBaseURL: cfg.Binance.BaseURL,
		WSBaseURL:   cfg.Binance.WSURL,
	})
	syms := make([]domain.Symbol, 0, len(cfg.Symbols))
	for _, s := range cfg.Symbols {
		syms = append(syms, domain.Symbol(s))
	}
	var pgPinger Pinger
	if pg != nil {
		pgPinger = pg
	}
	var rdbPinger Pinger
	if rdb != nil {
		rdbPinger = redisPinger{c: rdb}
	}

	var repo data.Repo
	if pg != nil {
		repo = data.NewPostgresRepo(pg)
	}
	var cache data.Cache
	if rdb != nil {
		cache = data.NewRedisCache(rdb, time.Minute)
	}
	marketSvc := market.NewService(cache, repo, syms)

	app := fiber.New(fiber.Config{
		DisableStartupMessage: true,
		ErrorHandler: func(c *fiber.Ctx, err error) error {
			slog.Error("unhandled fiber error", "service", "api", "err", err)
			return Err(c, fiber.StatusInternalServerError, "internal", "unexpected error")
		},
	})

	s := &Server{
		cfg:      cfg,
		app:      app,
		pg:       pgPinger,
		rdb:      rdbPinger,
		ai:       newAIClient(cfg.AI.BaseURL),
		authSvc:  o.Auth,
		settSvc:  o.Settings,
		alertSvc: o.Alerts,
	}

	s.mountMiddleware()
	s.mountRoutes(mgr, marketSvc, repo, pg, o)
	return s
}

type redisPinger struct{ c *goredis.Client }

func (p redisPinger) Ping(ctx context.Context) error {
	return p.c.Ping(ctx).Err()
}

// App returns the underlying *fiber.App, useful for testing with app.Test(req).
func (s *Server) App() *fiber.App { return s.app }

// Listen starts the Fiber server on the configured address (blocking).
func (s *Server) Listen() error {
	slog.Info("api listening", "service", "api", "addr", s.Addr())
	return s.app.Listen(s.Addr())
}

// Shutdown gracefully shuts down the server.
func (s *Server) Shutdown() error { return s.app.Shutdown() }

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
	s.app.Use(fiberrecover.New())
	s.app.Use(fiberrequestid.New())
	s.app.Use(fiberlogger.New(fiberlogger.Config{
		Format: "${time} ${status} ${method} ${path} request_id=${locals:requestid} dur=${latency}\n",
	}))
	s.app.Use(fibercors.New(fibercors.Config{
		AllowOrigins: "*",
		AllowMethods: "GET,POST,PUT,PATCH,DELETE,OPTIONS",
		AllowHeaders: "Authorization,Content-Type",
	}))
	s.app.Use(auth.Middleware(s.authSvc, isPublicPath))
}

func (s *Server) mountRoutes(
	mgr *runtime.Manager,
	marketSvc *market.Service,
	repo data.Repo,
	pg *pgxpool.Pool,
	o Options,
) {
	// Health
	s.app.Get("/healthz", s.handleHealthz)
	s.app.Get("/api/ai/healthz", s.handleAIHealthz)

	// Auth, Settings, Alerts — each package owns its router.go
	auth.RegisterRoutes(s.app, auth.NewHandler(o.Auth))
	settings.RegisterRoutes(s.app, settings.NewHandler(o.Settings))
	alert.RegisterRoutes(s.app, alert.NewHandler(o.Alerts))

	// Bot / Paper / Dashboard / Risk / Trades / BinanceKey / AI / Market
	handlers.RegisterRoutes(s.app, handlers.Deps{
		Manager:   mgr,
		MarketSvc: marketSvc,
		BinanceCfg: binance.Config{
			APIKey:      s.cfg.Binance.APIKey,
			APISecret:   s.cfg.Binance.APISecret,
			Testnet:     s.cfg.Binance.Testnet,
			RestBaseURL: s.cfg.Binance.BaseURL,
			WSBaseURL:   s.cfg.Binance.WSURL,
		},
		AIBaseURL: s.cfg.AI.BaseURL,
	})

	registry := strategy.NewRegistry()
	registry.Register(builtin.MACrossName, builtin.MACrossFactory)
	registry.Register(builtin.RSIName, builtin.RSIFactory)
	registry.Register(builtin.AIName, func(cfg strategy.RuleConfig) (strategy.Strategy, error) {
		client := aipkg.New(aipkg.Config{BaseURL: s.cfg.AI.BaseURL})
		interval := cfg.Params["interval"]
		if interval == "" {
			interval = "1m"
		}
		minConfidence := decimal.NewFromFloat(0.5)
		if raw := strings.TrimSpace(cfg.Params["min_confidence"]); raw != "" {
			parsed, err := decimal.NewFromString(raw)
			if err != nil {
				return nil, err
			}
			minConfidence = parsed
		}
		return builtin.NewAI(client, interval, minConfidence), nil
	})

	backtestStore := backtest.Store(backtest.NewMemoryStore())
	if pg != nil {
		backtestStore = backtest.NewPostgresStore(pg)
	}

	rsk := risk.NewEngine(risk.Policy{
		MaxPositionPct:      s.cfg.Risk.MaxPositionPct,
		MaxDailyDrawdownPct: s.cfg.Risk.MaxDailyDrawdownPct,
		MaxSlippageBps:      s.cfg.Risk.MaxSlippageBps,
		RequireStopLoss:     s.cfg.Risk.RequireStopLoss,
	})

	backtestClient := binance.New(binance.Config{
		APIKey:      s.cfg.Binance.APIKey,
		APISecret:   s.cfg.Binance.APISecret,
		Testnet:     s.cfg.Binance.Testnet,
		RestBaseURL: s.cfg.Binance.BaseURL,
		WSBaseURL:   s.cfg.Binance.WSURL,
	})
	backtest.RegisterRoutes(s.app, backtest.NewHandler(backtestStore, repo, registry, rsk).WithRemoteFetcher(backtestClient))

	// Debug
	s.app.Get("/debug/error", func(c *fiber.Ctx) error {
		return ErrDetails(c, fiber.StatusTeapot, "debug_forced_error",
			"forced error for envelope verification",
			map[string]interface{}{"reason": "debug endpoint"})
	})
}

// isPublicPath identifies routes that bypass JWT auth.
func isPublicPath(c *fiber.Ctx) bool {
	p := c.Path()
	switch p {
	case "/healthz",
		"/api/ai/healthz",
		"/api/auth/login",
		"/api/auth/register":
		return true
	}
	return strings.HasPrefix(p, "/healthz")
}

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
