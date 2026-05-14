package auth

import (
	"context"
	"strings"

	"github.com/gofiber/fiber/v2"
)

type ctxKey int

const ctxKeyClaims ctxKey = iota

// Middleware returns a Fiber handler that requires a valid JWT.
// skip is consulted first; if it returns true the request is passed through.
func Middleware(svc *Service, skip func(*fiber.Ctx) bool) fiber.Handler {
	return func(c *fiber.Ctx) error {
		if skip != nil && skip(c) {
			return c.Next()
		}
		h := c.Get("Authorization")
		if !strings.HasPrefix(strings.ToLower(h), "bearer ") {
			return c.Status(fiber.StatusUnauthorized).JSON(fiber.Map{
				"data":  nil,
				"error": fiber.Map{"code": "unauthorized", "message": "missing bearer token"},
			})
		}
		tok := strings.TrimSpace(h[7:])
		claims, err := svc.VerifyToken(tok)
		if err != nil {
			return c.Status(fiber.StatusUnauthorized).JSON(fiber.Map{
				"data":  nil,
				"error": fiber.Map{"code": "unauthorized", "message": "invalid or expired token"},
			})
		}
		c.SetUserContext(context.WithValue(c.UserContext(), ctxKeyClaims, claims))
		return c.Next()
	}
}

// ClaimsFromContext returns the parsed claims attached by Middleware.
func ClaimsFromContext(ctx context.Context) (*Claims, bool) {
	c, ok := ctx.Value(ctxKeyClaims).(*Claims)
	return c, ok
}

// RequireRole returns a Fiber middleware that rejects requests whose claims role
// is not in the provided allowed list.
func RequireRole(allowed ...Role) fiber.Handler {
	allowSet := make(map[Role]struct{}, len(allowed))
	for _, r := range allowed {
		allowSet[r] = struct{}{}
	}
	return func(c *fiber.Ctx) error {
		claims, ok := ClaimsFromContext(c.UserContext())
		if !ok {
			return c.Status(fiber.StatusUnauthorized).JSON(fiber.Map{
				"data":  nil,
				"error": fiber.Map{"code": "unauthorized", "message": "no auth context"},
			})
		}
		if _, ok := allowSet[claims.Role]; !ok {
			return c.Status(fiber.StatusForbidden).JSON(fiber.Map{
				"data":  nil,
				"error": fiber.Map{"code": "forbidden", "message": "insufficient role"},
			})
		}
		return c.Next()
	}
}
