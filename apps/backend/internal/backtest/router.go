package backtest

import "github.com/gofiber/fiber/v2"

// RegisterRoutes mounts backtest endpoints onto the Fiber app.
func RegisterRoutes(app *fiber.App, h *Handler) {
	app.Post("/api/backtest/run", h.run)
	app.Get("/api/backtest", h.list)
	app.Get("/api/backtest/:id", h.get)
}
