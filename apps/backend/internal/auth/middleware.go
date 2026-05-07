package auth

import (
	"context"
	"net/http"
	"strings"
)

type ctxKey int

const (
	ctxKeyClaims ctxKey = iota
)

// ResponseWriter is a minimal interface to write JSON errors. The api package
// has its own envelope writer; we duplicate just enough here to keep auth
// independent of internal/api (avoids import cycles).
type errorResponder func(w http.ResponseWriter, status int, code, msg string)

// PathSkipper decides whether a request bypasses auth (e.g. /healthz, /api/auth/login).
type PathSkipper func(r *http.Request) bool

// Middleware returns an HTTP middleware that requires a valid JWT.
// Skip is consulted first; if it returns true the request is passed through.
func Middleware(svc *Service, skip PathSkipper, write errorResponder) func(http.Handler) http.Handler {
	return func(next http.Handler) http.Handler {
		return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
			if skip != nil && skip(r) {
				next.ServeHTTP(w, r)
				return
			}
			h := r.Header.Get("Authorization")
			if !strings.HasPrefix(strings.ToLower(h), "bearer ") {
				write(w, http.StatusUnauthorized, "unauthorized", "missing bearer token")
				return
			}
			tok := strings.TrimSpace(h[len("Bearer "):])
			claims, err := svc.VerifyToken(tok)
			if err != nil {
				write(w, http.StatusUnauthorized, "unauthorized", "invalid or expired token")
				return
			}
			ctx := context.WithValue(r.Context(), ctxKeyClaims, claims)
			next.ServeHTTP(w, r.WithContext(ctx))
		})
	}
}

// ClaimsFromContext returns the parsed claims attached by Middleware.
func ClaimsFromContext(ctx context.Context) (*Claims, bool) {
	c, ok := ctx.Value(ctxKeyClaims).(*Claims)
	return c, ok
}

// RequireRole returns a middleware that rejects requests whose claims role is
// not in the provided allowed list.
func RequireRole(write errorResponder, allowed ...Role) func(http.Handler) http.Handler {
	allowSet := make(map[Role]struct{}, len(allowed))
	for _, r := range allowed {
		allowSet[r] = struct{}{}
	}
	return func(next http.Handler) http.Handler {
		return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
			c, ok := ClaimsFromContext(r.Context())
			if !ok {
				write(w, http.StatusUnauthorized, "unauthorized", "no auth context")
				return
			}
			if _, ok := allowSet[c.Role]; !ok {
				write(w, http.StatusForbidden, "forbidden", "insufficient role")
				return
			}
			next.ServeHTTP(w, r)
		})
	}
}
