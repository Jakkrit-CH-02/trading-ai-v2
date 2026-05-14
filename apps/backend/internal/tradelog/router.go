package tradelog

import "github.com/gofiber/fiber/v2"

// RegisterRoutes mounts trade log endpoints onto the Fiber app.
func RegisterRoutes(app *fiber.App, h *Handler) {
	app.Get("/api/trades", h.list)
	app.Get("/api/trades/summary", h.summary)
}
