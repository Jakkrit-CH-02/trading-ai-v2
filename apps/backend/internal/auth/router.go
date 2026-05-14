package auth

import "github.com/gofiber/fiber/v2"

// RegisterRoutes mounts auth endpoints onto the Fiber app.
// login and register are public; me and logout require a valid JWT (enforced
// by the global auth middleware in internal/api/server.go).
func RegisterRoutes(app *fiber.App, h *Handler) {
	app.Post("/api/auth/register", h.Register)
	app.Post("/api/auth/login", h.Login)
	app.Post("/api/auth/logout", h.Logout)
	app.Get("/api/auth/me", h.Me)

	// Admin-only: create a user as admin.
	admin := app.Group("/api/admin", RequireRole(RoleAdmin))
	admin.Post("/users", h.Register)
}
