package settings

import "github.com/gofiber/fiber/v2"

// RegisterRoutes mounts settings endpoints onto the Fiber app.
func RegisterRoutes(app *fiber.App, h *Handler) {
	app.Get("/api/settings", h.Get)
	app.Put("/api/settings", h.Put)
}
