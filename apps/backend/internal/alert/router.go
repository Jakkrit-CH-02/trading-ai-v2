package alert

import "github.com/gofiber/fiber/v2"

// RegisterRoutes mounts alert endpoints onto the Fiber app.
func RegisterRoutes(app *fiber.App, h *Handler) {
	app.Get("/api/alerts", h.List)
	app.Post("/api/alerts/:id/ack", h.Ack)
}
