package handlers

import (
	"github.com/gofiber/fiber/v2"

	"github.com/jakkrit-ch/trading-ai-v2/backend/internal/runtime"
)

type paper struct {
	mgr *runtime.Manager
}

func newPaper(mgr *runtime.Manager) *paper { return &paper{mgr: mgr} }

func (p *paper) portfolio(c *fiber.Ctx) error {
	return writeOK(c, p.mgr.Portfolio())
}

func (p *paper) trades(c *fiber.Ctx) error {
	trades := p.mgr.Trades()
	if trades == nil {
		trades = []runtime.TradeRecord{}
	}
	return writeOK(c, map[string]interface{}{"trades": trades})
}

func (p *paper) resetPortfolio(c *fiber.Ctx) error {
	p.mgr.ResetPortfolio()
	return writeOK(c, p.mgr.Portfolio())
}
