package settings

import (
	"errors"

	"github.com/gofiber/fiber/v2"
	"github.com/shopspring/decimal"

	"github.com/jakkrit-ch/trading-ai-v2/backend/internal/auth"
)

// Handler exposes settings HTTP endpoints.
type Handler struct {
	svc *Service
}

func NewHandler(svc *Service) *Handler { return &Handler{svc: svc} }

// dto is the wire representation. Decimals are sent as strings per project rule.
type dto struct {
	UserID              string `json:"user_id"`
	DefaultSymbol       string `json:"default_symbol"`
	DefaultTimeframe    string `json:"default_timeframe"`
	DefaultMode         string `json:"default_mode"`
	MaxPositionPct      string `json:"max_position_pct"`
	MaxDailyDrawdownPct string `json:"max_daily_drawdown_pct"`
	MaxSlippageBps      int    `json:"max_slippage_bps"`
	NotifyEmail         bool   `json:"notify_email"`
	NotifyWebhookURL    string `json:"notify_webhook_url"`
	UpdatedAt           int64  `json:"updated_at"`
}

func toDTO(s Settings) dto {
	return dto{
		UserID:              s.UserID,
		DefaultSymbol:       s.DefaultSymbol,
		DefaultTimeframe:    s.DefaultTimeframe,
		DefaultMode:         s.DefaultMode,
		MaxPositionPct:      s.MaxPositionPct.String(),
		MaxDailyDrawdownPct: s.MaxDailyDrawdownPct.String(),
		MaxSlippageBps:      s.MaxSlippageBps,
		NotifyEmail:         s.NotifyEmail,
		NotifyWebhookURL:    s.NotifyWebhookURL,
		UpdatedAt:           s.UpdatedAt.UnixMilli(),
	}
}

func fromDTO(d dto) (Settings, error) {
	pos, err := decimal.NewFromString(d.MaxPositionPct)
	if err != nil {
		return Settings{}, err
	}
	dd, err := decimal.NewFromString(d.MaxDailyDrawdownPct)
	if err != nil {
		return Settings{}, err
	}
	return Settings{
		DefaultSymbol:       d.DefaultSymbol,
		DefaultTimeframe:    d.DefaultTimeframe,
		DefaultMode:         d.DefaultMode,
		MaxPositionPct:      pos,
		MaxDailyDrawdownPct: dd,
		MaxSlippageBps:      d.MaxSlippageBps,
		NotifyEmail:         d.NotifyEmail,
		NotifyWebhookURL:    d.NotifyWebhookURL,
	}, nil
}

// Get handles GET /api/settings[?user_id=...]
func (h *Handler) Get(c *fiber.Ctx) error {
	claims, ok := auth.ClaimsFromContext(c.UserContext())
	if !ok {
		return errResp(c, fiber.StatusUnauthorized, "unauthorized", "no auth context")
	}
	target := c.Query("user_id")
	s, err := h.svc.Get(c.UserContext(), claims, target)
	if err != nil {
		return h.serviceErr(c, err)
	}
	return c.JSON(okEnv(toDTO(s)))
}

// Put handles PUT /api/settings[?user_id=...]
func (h *Handler) Put(c *fiber.Ctx) error {
	claims, ok := auth.ClaimsFromContext(c.UserContext())
	if !ok {
		return errResp(c, fiber.StatusUnauthorized, "unauthorized", "no auth context")
	}
	var d dto
	if err := c.BodyParser(&d); err != nil {
		return errResp(c, fiber.StatusBadRequest, "validation_failed", "invalid json")
	}
	in, err := fromDTO(d)
	if err != nil {
		return errResp(c, fiber.StatusBadRequest, "validation_failed", "invalid decimal value")
	}
	target := c.Query("user_id")
	if target == "" {
		target = d.UserID
	}
	out, err := h.svc.Update(c.UserContext(), claims, target, in)
	if err != nil {
		return h.serviceErr(c, err)
	}
	return c.JSON(okEnv(toDTO(out)))
}

func (h *Handler) serviceErr(c *fiber.Ctx, err error) error {
	switch {
	case errors.Is(err, ErrUnauthenticated):
		return errResp(c, fiber.StatusUnauthorized, "unauthorized", err.Error())
	case errors.Is(err, ErrForbidden):
		return errResp(c, fiber.StatusForbidden, "forbidden", "not allowed to access these settings")
	case errors.Is(err, ErrValidation):
		return errResp(c, fiber.StatusBadRequest, "validation_failed", err.Error())
	case errors.Is(err, ErrNotFound):
		return errResp(c, fiber.StatusNotFound, "not_found", "settings not found")
	default:
		return errResp(c, fiber.StatusInternalServerError, "internal", "settings request failed")
	}
}

func okEnv(data interface{}) fiber.Map {
	return fiber.Map{"data": data, "error": nil}
}

func errResp(c *fiber.Ctx, status int, code, msg string) error {
	return c.Status(status).JSON(fiber.Map{
		"data":  nil,
		"error": fiber.Map{"code": code, "message": msg},
	})
}
