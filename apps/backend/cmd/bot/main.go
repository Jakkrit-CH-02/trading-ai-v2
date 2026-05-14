package main

import (
	"context"
	"flag"
	"log/slog"
	"os"
	"os/signal"
	"syscall"

	"github.com/shopspring/decimal"

	"github.com/jakkrit-ch/trading-ai-v2/backend/internal/binance"
	"github.com/jakkrit-ch/trading-ai-v2/backend/internal/domain"
	"github.com/jakkrit-ch/trading-ai-v2/backend/internal/order"
	"github.com/jakkrit-ch/trading-ai-v2/backend/internal/paper"
	"github.com/jakkrit-ch/trading-ai-v2/backend/internal/platform/config"
	"github.com/jakkrit-ch/trading-ai-v2/backend/internal/risk"
	"github.com/jakkrit-ch/trading-ai-v2/backend/internal/runtime"
	"github.com/jakkrit-ch/trading-ai-v2/backend/internal/strategy"
	"github.com/jakkrit-ch/trading-ai-v2/backend/internal/strategy/builtin"
)

const (
	klineInterval    = "1m"
	initialCashUSDT  = 10_000
	warmupBars       = 50 // enough to seed EMA slow period (default 21) + crossover detection
	positionFraction = "0.01"
	stopLossFraction = "0.02"
)

func main() {
	cfgPath := flag.String("config", "config/config.dev.yaml", "path to config YAML")
	flag.Parse()

	logger := slog.New(slog.NewTextHandler(os.Stdout, &slog.HandlerOptions{Level: slog.LevelInfo}))
	slog.SetDefault(logger)

	cfg, err := config.Load(*cfgPath)
	if err != nil {
		slog.Error("bot: config load failed", "err", err)
		os.Exit(1)
	}

	slog.Info("bot starting",
		"service", "bot",
		"mode", cfg.Mode,
		"symbols", cfg.Symbols,
		"interval", klineInterval,
	)

	bc := binance.New(binance.Config{
		APIKey:    cfg.Binance.APIKey,
		APISecret: cfg.Binance.APISecret,
		Testnet:   cfg.Binance.Testnet,
	})

	ctx, stop := signal.NotifyContext(context.Background(), os.Interrupt, syscall.SIGTERM)
	defer stop()

	policy := risk.PolicyFromConfig(cfg.Risk)
	riskEngine := risk.NewEngine(policy)

	pipeCfg := runtime.PipelineConfig{
		PositionFraction: decimal.RequireFromString(positionFraction),
		StopLossFraction: decimal.RequireFromString(stopLossFraction),
	}

	controllers := make([]*runtime.Controller, 0, len(cfg.Symbols))

	for _, sym := range cfg.Symbols {
		symbol := domain.Symbol(sym)

		paperEngine := paper.NewEngine(decimal.NewFromInt(initialCashUSDT))
		router := order.NewRouter(paperEngine, nil)
		manager := order.NewManager(router, domain.ModePaper)

		macross := builtin.NewMACross(9, 21)
		stratEngine := strategy.NewEngine(macross)

		// Warm the strategy with recent historical bars so it produces signals immediately.
		warmBars, err := bc.GetKlines(ctx, binance.KlinesQuery{
			Symbol:   sym,
			Interval: klineInterval,
			Limit:    warmupBars,
		})
		if err != nil {
			slog.Warn("bot: warmup klines failed, starting cold",
				"service", "bot",
				"symbol", sym,
				"err", err,
			)
		}

		sizer := runtime.FixedFractionSizer(pipeCfg)
		pipe := runtime.NewPipeline(stratEngine, riskEngine, manager, paperEngine, paperEngine, paperEngine, sizer)

		if len(warmBars) > 0 {
			if err := pipe.Warm(ctx, warmBars); err != nil {
				slog.Warn("bot: pipeline warm failed",
					"service", "bot",
					"symbol", sym,
					"err", err,
				)
			} else {
				slog.Info("bot: pipeline warmed",
					"service", "bot",
					"symbol", sym,
					"bars", len(warmBars),
				)
			}
		}

		barsCh := bc.KlineStream(ctx, symbol, klineInterval)
		ctrl := runtime.NewController(pipe, barsCh, domain.ModePaper, symbol)
		ctrl.WithFlattener(paperEngine)

		if err := ctrl.Start(ctx); err != nil {
			slog.Error("bot: controller start failed",
				"service", "bot",
				"symbol", sym,
				"err", err,
			)
			os.Exit(1)
		}

		controllers = append(controllers, ctrl)
		slog.Info("bot: pipeline running",
			"service", "bot",
			"mode", "paper",
			"symbol", sym,
			"interval", klineInterval,
		)
	}

	<-ctx.Done()
	slog.Info("bot shutting down", "service", "bot")

	stopCtx := context.Background()
	for i, ctrl := range controllers {
		if err := ctrl.Stop(stopCtx); err != nil {
			slog.Error("bot: controller stop failed",
				"service", "bot",
				"symbol", cfg.Symbols[i],
				"err", err,
			)
		}
	}
}
