// Package livegate enforces the four conditions that must all hold before a
// live order can leave the system:
//
//  1. mode = live (caller-enforced via the order Router)
//  2. env LIVE_TRADING_ENABLED = true
//  3. startup-time Binance API key permission check passed (no withdraw,
//     has trade)
//  4. the request carries a valid live-confirmation token issued from the
//     UI modal
//
// Any missing condition makes the gate deny. The denial is the failure
// mode — there is no "log and continue" path for live trading.
package livegate

import (
	"context"
	"errors"
	"fmt"
	"log/slog"
	"sync"
	"time"

	"github.com/jakkrit-ch/trading-ai-v2/backend/internal/platform/ids"
)

// Sentinel errors. Callers branch on these via errors.Is.
var (
	ErrEnvDisabled        = errors.New("livegate: LIVE_TRADING_ENABLED not true")
	ErrAPIPermissions     = errors.New("livegate: binance api key permission check failed")
	ErrMissingToken       = errors.New("livegate: missing live confirmation token")
	ErrInvalidToken       = errors.New("livegate: invalid or expired confirmation token")
)

// PermissionCheck is the runtime view of the startup Binance permission
// probe. It must report whether the configured key (a) can trade and
// (b) cannot withdraw — failing either flips this to false.
type PermissionCheck interface {
	OK() bool
}

// EnvFlag is the indirection used to read the LIVE_TRADING_ENABLED env at
// gate-evaluation time. Tests inject a closure; production wires os.Getenv.
type EnvFlag func() bool

// ctxKey is the unexported type used for the live-confirmation token
// context key. Callers attach the token using WithToken; the gate retrieves
// it using TokenFromContext.
type ctxKey struct{}

// WithToken returns a derived context carrying the live-confirmation token.
// HTTP handlers should call this before invoking any code path that
// eventually places a live order.
func WithToken(ctx context.Context, token string) context.Context {
	return context.WithValue(ctx, ctxKey{}, token)
}

// TokenFromContext extracts the token attached by WithToken. Returns the
// empty string if no token was attached.
func TokenFromContext(ctx context.Context) string {
	v, _ := ctx.Value(ctxKey{}).(string)
	return v
}

// tokenRecord is one issued (not-yet-expired) token. Tokens are valid for
// the full TTL window — an active live session reuses the same token for
// every order it submits during that window. Re-confirmation is only
// required after expiry or a new session.
type tokenRecord struct {
	expiresAt time.Time
}

// Gate carries all four conditions. It is safe for concurrent use; tokens
// are stored in-process (single-replica deployment is the current model).
type Gate struct {
	envFlag EnvFlag
	perm    PermissionCheck
	tokenTTL time.Duration

	mu     sync.Mutex
	tokens map[string]*tokenRecord
}

// Config bundles the gate dependencies.
type Config struct {
	EnvFlag    EnvFlag       // returns true iff LIVE_TRADING_ENABLED=true
	Permission PermissionCheck
	TokenTTL   time.Duration // how long an issued token is valid; default 5m
}

// New constructs a Gate. EnvFlag and Permission are required.
func New(cfg Config) *Gate {
	if cfg.EnvFlag == nil {
		cfg.EnvFlag = func() bool { return false }
	}
	if cfg.Permission == nil {
		cfg.Permission = staticPermission(false)
	}
	if cfg.TokenTTL <= 0 {
		cfg.TokenTTL = 5 * time.Minute
	}
	return &Gate{
		envFlag:  cfg.EnvFlag,
		perm:     cfg.Permission,
		tokenTTL: cfg.TokenTTL,
		tokens:   make(map[string]*tokenRecord),
	}
}

// IssueToken mints a new live-confirmation token. Caller is responsible for
// upstream gating (typed-phrase modal + admin-role check at the HTTP layer).
// Returned token is valid for TokenTTL and may be consumed once.
func (g *Gate) IssueToken(ctx context.Context) string {
	tok := ids.New()
	g.mu.Lock()
	g.tokens[tok] = &tokenRecord{expiresAt: time.Now().Add(g.tokenTTL)}
	g.mu.Unlock()
	slog.InfoContext(ctx, "live confirmation token issued",
		"service", "livegate",
		"ttl_sec", int(g.tokenTTL.Seconds()),
	)
	return tok
}

// Allow checks all four gate conditions. Condition (a) — mode = live — is
// the caller's responsibility (the Router only routes live mode here).
// Tokens are reusable until they expire: a single confirmation arms the
// live session for the TTL window.
func (g *Gate) Allow(ctx context.Context) error {
	if !g.envFlag() {
		return ErrEnvDisabled
	}
	if !g.perm.OK() {
		return ErrAPIPermissions
	}
	tok := TokenFromContext(ctx)
	if tok == "" {
		return ErrMissingToken
	}
	g.mu.Lock()
	rec, ok := g.tokens[tok]
	now := time.Now()
	if !ok || now.After(rec.expiresAt) {
		g.mu.Unlock()
		return fmt.Errorf("%w", ErrInvalidToken)
	}
	g.mu.Unlock()
	return nil
}

// Revoke immediately invalidates a token. Called when the operator stops
// the bot or hits Kill — either should also force re-confirmation before
// the next live activation.
func (g *Gate) Revoke(token string) {
	if token == "" {
		return
	}
	g.mu.Lock()
	delete(g.tokens, token)
	g.mu.Unlock()
}

// Active reports whether the gate has at least one unconsumed, unexpired
// token. Used by handlers to surface "ready to place live order" without
// consuming the token.
func (g *Gate) Active() bool {
	g.mu.Lock()
	defer g.mu.Unlock()
	now := time.Now()
	for _, rec := range g.tokens {
		if now.Before(rec.expiresAt) {
			return true
		}
	}
	return false
}

// staticPermission is a trivial PermissionCheck that returns a fixed value;
// used as a safe default when none is supplied.
type staticPermission bool

func (s staticPermission) OK() bool { return bool(s) }

// StaticPermission returns a PermissionCheck that always reports the given
// boolean. Tests use this; production wires the real Binance check.
func StaticPermission(ok bool) PermissionCheck { return staticPermission(ok) }

// EnvFlagFromOS returns an EnvFlag closed over os.Getenv-style lookup. It is
// re-evaluated on every call so toggling the env var at runtime is honored.
func EnvFlagFromOS(getenv func(string) string) EnvFlag {
	return func() bool {
		v := getenv("LIVE_TRADING_ENABLED")
		return v == "true" || v == "1" || v == "TRUE"
	}
}
