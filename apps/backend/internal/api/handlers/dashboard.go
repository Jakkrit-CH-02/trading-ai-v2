package handlers

import "github.com/gofiber/fiber/v2"

type dashboard struct {
	bot *Bot
}

func newDashboard(bot *Bot) *dashboard { return &dashboard{bot: bot} }

func (d *dashboard) summary(c *fiber.Ctx) error {
	s := d.bot.mgr.BotStatus()
	return writeOK(c, map[string]interface{}{
		"bot_state":      string(s.State),
		"equity":         nil,
		"pnl_today":      nil,
		"open_positions": []interface{}{},
	})
}
