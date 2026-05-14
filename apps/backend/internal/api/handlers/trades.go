package handlers

import "github.com/gofiber/fiber/v2"

type trades struct{}

func newTrades() *trades { return &trades{} }

func (t *trades) list(c *fiber.Ctx) error {
	return writeOK(c, map[string]interface{}{
		"trades": []interface{}{},
		"total":  0,
		"limit":  100,
		"offset": 0,
	})
}
