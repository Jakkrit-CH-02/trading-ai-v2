package main

import (
	"context"
	"flag"
	"log/slog"
	"os"
	"os/signal"
	"syscall"

	"github.com/jakkrit-ch/trading-ai-v2/backend/internal/api"
	"github.com/jakkrit-ch/trading-ai-v2/backend/internal/platform/config"
	"github.com/jakkrit-ch/trading-ai-v2/backend/internal/storage/postgres"
	"github.com/jakkrit-ch/trading-ai-v2/backend/internal/storage/redis"
)

func main() {
	configPath := flag.String("config", "config/config.dev.yaml", "path to config file")
	flag.Parse()

	logger := slog.New(slog.NewTextHandler(os.Stdout, &slog.HandlerOptions{Level: slog.LevelInfo}))
	slog.SetDefault(logger)

	cfg, err := config.Load(*configPath)
	if err != nil {
		slog.Error("config load failed", "service", "api", "err", err)
		os.Exit(1)
	}
	slog.Info("config loaded", "service", "api", "env", cfg.Env, "mode", cfg.Mode)

	rootCtx, cancel := context.WithCancel(context.Background())
	defer cancel()

	// Postgres — best-effort during foundation phase. We still serve /healthz if it's down.
	pool, err := postgres.New(rootCtx, cfg.DB)
	if err != nil {
		slog.Warn("postgres unavailable, continuing without it", "service", "api", "err", err)
	} else {
		slog.Info("postgres connected", "service", "api")
		defer pool.Close()
	}

	// Redis — same best-effort posture.
	rdb, err := redis.New(rootCtx, cfg.Redis)
	if err != nil {
		slog.Warn("redis unavailable, continuing without it", "service", "api", "err", err)
	} else {
		slog.Info("redis connected", "service", "api")
		defer func() { _ = rdb.Close() }()
	}

	server := api.New(cfg, pool, rdb)

	stop := make(chan os.Signal, 1)
	signal.Notify(stop, os.Interrupt, syscall.SIGTERM)

	go func() {
		select {
		case <-stop:
		case <-rootCtx.Done():
		}
		slog.Info("shutting down", "service", "api")
		if err := server.Shutdown(); err != nil {
			slog.Error("shutdown error", "service", "api", "err", err)
		}
	}()

	if err := server.Listen(); err != nil {
		slog.Error("server failed", "service", "api", "err", err)
		os.Exit(1)
	}
}
