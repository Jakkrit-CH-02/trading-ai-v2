package handlers

import (
	"strings"
	"time"

	"github.com/gofiber/fiber/v2"

	"github.com/jakkrit-ch/trading-ai-v2/backend/internal/binance"
)

type binanceKey struct {
	cfg binance.Config
}

func newBinanceKey(cfg binance.Config) *binanceKey { return &binanceKey{cfg: cfg} }

// status reports whether an API key is configured and which environment it targets.
// It does NOT make a network call; call test for live validation.
func (b *binanceKey) status(c *fiber.Ctx) error {
	configured := b.cfg.APIKey != ""
	maskedKey := ""
	if configured {
		maskedKey = maskKey(b.cfg.APIKey)
	}
	return writeOK(c, map[string]interface{}{
		"configured":      configured,
		"masked_key":      maskedKey,
		"permissions":     map[string]bool{"read": false, "spot_trade": false, "withdraw": false},
		"testnet":         b.cfg.Testnet,
		"last_checked_ms": 0,
	})
}

// test dials Binance, validates the API key via GET /api/v3/account,
// and returns the actual permission set.
func (b *binanceKey) test(c *fiber.Ctx) error {
	if b.cfg.APIKey == "" || b.cfg.APISecret == "" {
		return writeError(c, fiber.StatusBadRequest, "validation_failed", "API key and secret are not configured")
	}

	ctx := c.UserContext()
	client := binance.New(b.cfg)
	if err := client.SyncTime(ctx); err != nil {
		return writeError(c, fiber.StatusBadGateway, "binance_unreachable", "failed to reach Binance: "+err.Error())
	}

	perms, err := client.CheckPermissions(ctx)
	if err != nil {
		return writeError(c, fiber.StatusBadGateway, "binance_auth_failed", "API key validation failed: "+err.Error())
	}

	return writeOK(c, map[string]interface{}{
		"configured": true,
		"masked_key": maskKey(b.cfg.APIKey),
		"permissions": map[string]bool{
			"read":       true,
			"spot_trade": perms.CanTrade,
			"withdraw":   perms.CanWithdraw,
		},
		"testnet":         b.cfg.Testnet,
		"last_checked_ms": time.Now().UnixMilli(),
	})
}

func maskKey(key string) string {
	if len(key) <= 8 {
		return strings.Repeat("•", len(key))
	}
	return key[:4] + strings.Repeat("•", len(key)-8) + key[len(key)-4:]
}
