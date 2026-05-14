package tradelog

import (
	"strconv"

	"github.com/gofiber/fiber/v2"

	"github.com/jakkrit-ch/trading-ai-v2/backend/internal/domain"
	"github.com/jakkrit-ch/trading-ai-v2/backend/internal/platform/timex"
)

const (
	defaultListLimit = 100
	maxListLimit     = 1000
)

// Handler exposes the trade log over HTTP.
type Handler struct{ svc *Service }

func NewHandler(svc *Service) *Handler { return &Handler{svc: svc} }

// ListResponse is the wire DTO for GET /api/trades.
type ListResponse struct {
	Trades []Record `json:"trades"`
	Total  int      `json:"total"`
	Limit  int      `json:"limit"`
	Offset int      `json:"offset"`
}

func (h *Handler) list(c *fiber.Ctx) error {
	f := Filter{
		Mode:     domain.Mode(c.Query("mode")),
		Symbol:   domain.Symbol(c.Query("symbol")),
		Side:     domain.Side(c.Query("side")),
		Strategy: c.Query("strategy"),
	}

	if v := c.Query("from_ms"); v != "" {
		n, err := strconv.ParseInt(v, 10, 64)
		if err != nil || n < 0 {
			return errResp(c, fiber.StatusBadRequest, "validation_failed", "from_ms must be a non-negative integer")
		}
		f.FromMs = n
	}
	if v := c.Query("to_ms"); v != "" {
		n, err := strconv.ParseInt(v, 10, 64)
		if err != nil || n < 0 {
			return errResp(c, fiber.StatusBadRequest, "validation_failed", "to_ms must be a non-negative integer")
		}
		f.ToMs = n
	}

	limit := defaultListLimit
	if v := c.Query("limit"); v != "" {
		n, err := strconv.Atoi(v)
		if err != nil || n <= 0 {
			return errResp(c, fiber.StatusBadRequest, "validation_failed", "limit must be a positive integer")
		}
		if n > maxListLimit {
			n = maxListLimit
		}
		limit = n
	}
	f.Limit = limit

	offset := 0
	if v := c.Query("offset"); v != "" {
		n, err := strconv.Atoi(v)
		if err != nil || n < 0 {
			return errResp(c, fiber.StatusBadRequest, "validation_failed", "offset must be a non-negative integer")
		}
		offset = n
	}
	f.Offset = offset

	records, total, err := h.svc.List(c.UserContext(), f)
	if err != nil {
		return errResp(c, fiber.StatusInternalServerError, "internal", err.Error())
	}
	return c.JSON(okEnv(ListResponse{
		Trades: records,
		Total:  total,
		Limit:  limit,
		Offset: offset,
	}))
}

func (h *Handler) summary(c *fiber.Ctx) error {
	p := Period(c.Query("period"))
	switch p {
	case "":
		p = PeriodDay
	case PeriodDay, PeriodWeek, PeriodAll:
	default:
		return errResp(c, fiber.StatusBadRequest, "validation_failed", "period must be one of: day, week, all")
	}

	sum, err := h.svc.Summary(c.UserContext(), p, timex.NowMs())
	if err != nil {
		return errResp(c, fiber.StatusInternalServerError, "internal", err.Error())
	}
	return c.JSON(okEnv(sum))
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
