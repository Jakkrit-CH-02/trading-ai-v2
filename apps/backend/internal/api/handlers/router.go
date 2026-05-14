package handlers

import (
	"github.com/gofiber/fiber/v2"

	"github.com/jakkrit-ch/trading-ai-v2/backend/internal/binance"
	"github.com/jakkrit-ch/trading-ai-v2/backend/internal/data/market"
	"github.com/jakkrit-ch/trading-ai-v2/backend/internal/runtime"
)

// Deps carries the shared dependencies wired by the API server.
type Deps struct {
	Manager    *runtime.Manager
	MarketSvc  *market.Service
	BinanceCfg binance.Config
	AIBaseURL  string
}

// RegisterRoutes mounts all handler-package routes onto the Fiber app.
func RegisterRoutes(app *fiber.App, d Deps) {
	bot := newBot(d.Manager)
	pap := newPaper(d.Manager)
	dash := newDashboard(bot)
	ri := newRisk(bot)
	tr := newTrades()
	bkey := newBinanceKey(d.BinanceCfg)
	ai := newAIProxy(d.AIBaseURL)
	mkt := newMarket(d.MarketSvc)

	// Bot control
	app.Get("/api/bot/status", bot.status)
	app.Post("/api/bot/start", bot.start)
	app.Post("/api/bot/stop", bot.stop)
	app.Post("/api/bot/pause", bot.pause)
	app.Post("/api/bot/kill", bot.kill)
	app.Post("/api/bot/reset", bot.reset)
	app.Post("/api/bot/live-confirm", bot.liveConfirm)
	app.Post("/api/bot/inject-bar", bot.injectBar) // dev/test only

	// Dashboard
	app.Get("/api/dashboard/summary", dash.summary)

	// Risk
	app.Get("/api/risk/snapshot", ri.snapshot)

	// Trades
	app.Get("/api/trades", tr.list)

	// Paper trading
	app.Get("/api/paper/portfolio", pap.portfolio)
	app.Get("/api/paper/trades", pap.trades)
	app.Post("/api/paper/reset", pap.resetPortfolio)

	// Binance key management
	app.Get("/api/settings/binance-key/status", bkey.status)
	app.Post("/api/settings/binance-key/test", bkey.test)

	// AI service proxy
	app.Post("/api/ai/datasets/build", ai.buildDataset)
	app.Post("/api/ai/features/compute", ai.computeFeatures)
	app.Post("/api/ai/training/run", ai.runTraining)
	app.Get("/api/ai/training/:id", ai.getTrainingJob)
	app.Get("/api/ai/models", ai.listModels)
	app.Post("/api/ai/models/:id/promote", ai.promoteModel)
	app.Post("/api/ai/predict", ai.predict)
	app.Post("/api/ai/predict/reload", ai.reloadModel)

	// Market data
	app.Get("/api/market/symbols", mkt.symbols)
	app.Get("/api/market/candles", mkt.candles)
	app.Get("/api/market/snapshot", mkt.snapshot)
}

// writeOK writes a success envelope.
func writeOK(c *fiber.Ctx, data interface{}) error {
	return c.JSON(fiber.Map{"data": data, "error": nil})
}

// writeError writes a failure envelope with the given HTTP status.
func writeError(c *fiber.Ctx, status int, code, msg string) error {
	return c.Status(status).JSON(fiber.Map{
		"data":  nil,
		"error": fiber.Map{"code": code, "message": msg},
	})
}
