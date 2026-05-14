package handlers

import (
	"github.com/gofiber/fiber/v2"
	"github.com/shopspring/decimal"

	"github.com/jakkrit-ch/trading-ai-v2/backend/internal/domain"
	"github.com/jakkrit-ch/trading-ai-v2/backend/internal/platform/timex"
	"github.com/jakkrit-ch/trading-ai-v2/backend/internal/runtime"
)

type startRequest struct {
	Mode      string `json:"mode"`
	Strategy  string `json:"strategy"`
	Symbol    string `json:"symbol"`
	Timeframe string `json:"timeframe"`
	Risk      struct {
		MaxPositionPct      float64 `json:"max_position_pct"`
		MaxDailyDrawdownPct float64 `json:"max_daily_drawdown_pct"`
		MaxSlippageBps      int     `json:"max_slippage_bps"`
		StopLossFraction    float64 `json:"stop_loss_fraction"`
	} `json:"risk"`
	Confirmed bool `json:"confirmed,omitempty"`
}

// Bot handles bot control endpoints using the runtime Manager.
type Bot struct {
	mgr *runtime.Manager
}

func newBot(mgr *runtime.Manager) *Bot { return &Bot{mgr: mgr} }

func (b *Bot) status(c *fiber.Ctx) error {
	s := b.mgr.BotStatus()
	return writeOK(c, map[string]interface{}{
		"state":       string(s.State),
		"mode":        string(s.Mode),
		"symbol":      string(s.Symbol),
		"last_signal": s.LastSignal,
		"last_error":  s.LastError,
	})
}

func (b *Bot) start(c *fiber.Ctx) error {
	var req startRequest
	if err := c.BodyParser(&req); err != nil {
		return writeError(c, fiber.StatusBadRequest, "validation_failed", "invalid request body")
	}
	if req.Mode == "live" && !req.Confirmed {
		return writeError(c, fiber.StatusForbidden, "forbidden", "live mode requires confirmation")
	}
	if req.Mode == "backtest" {
		return writeError(c, fiber.StatusBadRequest, "validation_failed", "historical backtests must be run from /backtest")
	}
	if req.Symbol == "" {
		return writeError(c, fiber.StatusBadRequest, "validation_failed", "symbol required")
	}
	if req.Timeframe == "" {
		req.Timeframe = "1m"
	}

	mgrReq := runtime.StartRequest{
		Mode:             domain.Mode(req.Mode),
		Strategy:         req.Strategy,
		Symbol:           domain.Symbol(req.Symbol),
		Timeframe:        req.Timeframe,
		MaxPositionPct:   decimal.NewFromFloat(req.Risk.MaxPositionPct),
		MaxDailyDrawdown: decimal.NewFromFloat(req.Risk.MaxDailyDrawdownPct),
		MaxSlippageBps:   req.Risk.MaxSlippageBps,
		StopLossFraction: decimal.NewFromFloat(req.Risk.StopLossFraction),
	}
	if mgrReq.MaxPositionPct.IsZero() {
		mgrReq.MaxPositionPct = decimal.NewFromFloat(0.02)
	}
	if mgrReq.MaxDailyDrawdown.IsZero() {
		mgrReq.MaxDailyDrawdown = decimal.NewFromFloat(0.05)
	}
	if mgrReq.MaxSlippageBps == 0 {
		mgrReq.MaxSlippageBps = 30
	}
	if mgrReq.StopLossFraction.IsZero() {
		mgrReq.StopLossFraction = decimal.NewFromFloat(0.05)
	}

	if err := b.mgr.Start(c.UserContext(), mgrReq); err != nil {
		code, status := botErrCode(err)
		return writeError(c, status, code, err.Error())
	}
	return writeOK(c, b.mgr.BotStatus())
}

func (b *Bot) stop(c *fiber.Ctx) error {
	if err := b.mgr.Stop(c.UserContext()); err != nil {
		code, status := botErrCode(err)
		return writeError(c, status, code, err.Error())
	}
	return writeOK(c, b.mgr.BotStatus())
}

func (b *Bot) pause(c *fiber.Ctx) error {
	if err := b.mgr.Pause(c.UserContext()); err != nil {
		code, status := botErrCode(err)
		return writeError(c, status, code, err.Error())
	}
	return writeOK(c, b.mgr.BotStatus())
}

func (b *Bot) kill(c *fiber.Ctx) error {
	if err := b.mgr.Kill(c.UserContext()); err != nil {
		code, status := botErrCode(err)
		return writeError(c, status, code, err.Error())
	}
	return writeOK(c, b.mgr.BotStatus())
}

func (b *Bot) reset(c *fiber.Ctx) error {
	if err := b.mgr.Reset(c.UserContext()); err != nil {
		code, status := botErrCode(err)
		return writeError(c, status, code, err.Error())
	}
	return writeOK(c, b.mgr.BotStatus())
}

func (b *Bot) liveConfirm(c *fiber.Ctx) error {
	var req struct {
		Phrase string `json:"phrase"`
	}
	if err := c.BodyParser(&req); err != nil {
		return writeError(c, fiber.StatusBadRequest, "validation_failed", "invalid body")
	}
	if req.Phrase != "I UNDERSTAND THE RISK" {
		return writeError(c, fiber.StatusBadRequest, "validation_failed", "confirmation phrase incorrect")
	}
	return writeOK(c, map[string]string{"token": "stub-live-token"})
}

// injectBar accepts a synthetic bar and feeds it through the running pipeline.
// Intended for development/testing only — use to trigger a signal without
// waiting for a real candle to close.
func (b *Bot) injectBar(c *fiber.Ctx) error {
	var req struct {
		Price string `json:"price"`
	}
	if err := c.BodyParser(&req); err != nil || req.Price == "" {
		return writeError(c, fiber.StatusBadRequest, "validation_failed", "price required")
	}
	price, err := decimal.NewFromString(req.Price)
	if err != nil || price.IsZero() || price.IsNegative() {
		return writeError(c, fiber.StatusBadRequest, "validation_failed", "price must be a positive decimal string")
	}

	status := b.mgr.BotStatus()
	bar := domain.Bar{
		Symbol:    status.Symbol,
		Interval:  "1m",
		OpenTime:  timex.NowMs() - 60_000,
		CloseTime: timex.NowMs(),
		Open:      price,
		High:      price,
		Low:       price,
		Close:     price,
		Volume:    decimal.NewFromInt(1),
	}
	sig, err := b.mgr.InjectBar(c.UserContext(), bar)
	if err != nil {
		code, httpStatus := botErrCode(err)
		return writeError(c, httpStatus, code, err.Error())
	}
	return writeOK(c, map[string]interface{}{
		"injected_price": price.String(),
		"symbol":         string(status.Symbol),
		"signal": map[string]interface{}{
			"id":         sig.ID,
			"action":     string(sig.Action),
			"reason":     sig.Reason,
			"strength":   sig.Strength.String(),
			"strategy":   sig.Strategy,
			"created_ms": sig.CreatedMs,
		},
	})
}

func botErrCode(err error) (code string, status int) {
	switch err {
	case runtime.ErrAlreadyRunning:
		return "validation_failed", fiber.StatusConflict
	case runtime.ErrNotRunning:
		return "validation_failed", fiber.StatusConflict
	case runtime.ErrHalted:
		return "forbidden", fiber.StatusForbidden
	default:
		return "internal_error", fiber.StatusInternalServerError
	}
}
