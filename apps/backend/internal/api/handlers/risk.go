package handlers

import (
	"time"

	"github.com/gofiber/fiber/v2"
)

type risk struct {
	bot *Bot
}

func newRisk(bot *Bot) *risk { return &risk{bot: bot} }

func (ri *risk) snapshot(c *fiber.Ctx) error {
	s := ri.bot.mgr.BotStatus()
	return writeOK(c, map[string]interface{}{
		"state":                  string(s.State),
		"max_position_pct":       "0.02",
		"max_daily_drawdown_pct": "0.05",
		"max_slippage_bps":       30,
		"equity":                 "10000.00",
		"initial_equity":         "10000.00",
		"cash":                   "10000.00",
		"exposure":               "0.00",
		"exposure_pct":           "0.000000",
		"daily_pnl":              "0.00",
		"daily_drawdown_pct":     "0.000000",
		"open_positions":         0,
		"largest_position_pct":   "0.000000",
		"positions":              []interface{}{},
		"updated_ms":             time.Now().UnixMilli(),
	})
}
