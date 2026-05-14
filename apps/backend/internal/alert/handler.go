package alert

import (
	"errors"

	"github.com/gofiber/fiber/v2"
)

// Handler exposes alert HTTP endpoints.
type Handler struct {
	svc *Service
}

func NewHandler(svc *Service) *Handler { return &Handler{svc: svc} }

type dto struct {
	ID        string `json:"id"`
	Type      string `json:"type"`
	Severity  string `json:"severity"`
	Message   string `json:"message"`
	Entity    string `json:"entity"`
	Read      bool   `json:"read"`
	CreatedAt int64  `json:"created_at"`
}

func toDTO(a Alert) dto {
	return dto{
		ID:        a.ID,
		Type:      string(a.Type),
		Severity:  string(a.Severity),
		Message:   a.Message,
		Entity:    a.Entity,
		Read:      a.Read,
		CreatedAt: a.CreatedAt.UnixMilli(),
	}
}

// List handles GET /api/alerts
func (h *Handler) List(c *fiber.Ctx) error {
	items, err := h.svc.List(c.UserContext(), 200)
	if err != nil {
		return errResp(c, fiber.StatusInternalServerError, "internal", "list alerts failed")
	}
	out := make([]dto, 0, len(items))
	for _, a := range items {
		out = append(out, toDTO(a))
	}
	return c.JSON(okEnv(out))
}

// Ack handles POST /api/alerts/:id/ack
func (h *Handler) Ack(c *fiber.Ctx) error {
	id := c.Params("id")
	if id == "" {
		return errResp(c, fiber.StatusBadRequest, "validation_failed", "id required")
	}
	if err := h.svc.Ack(c.UserContext(), id); err != nil {
		switch {
		case errors.Is(err, ErrNotFound):
			return errResp(c, fiber.StatusNotFound, "not_found", "alert not found")
		case errors.Is(err, ErrValidation):
			return errResp(c, fiber.StatusBadRequest, "validation_failed", err.Error())
		default:
			return errResp(c, fiber.StatusInternalServerError, "internal", "ack failed")
		}
	}
	return c.JSON(okEnv(map[string]string{"id": id, "status": "acked"}))
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
