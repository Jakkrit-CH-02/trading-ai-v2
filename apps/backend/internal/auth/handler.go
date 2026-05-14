package auth

import (
	"errors"

	"github.com/gofiber/fiber/v2"
)

// Handler exposes auth HTTP endpoints.
type Handler struct {
	svc *Service
}

func NewHandler(svc *Service) *Handler { return &Handler{svc: svc} }

type registerReq struct {
	Username string `json:"username"`
	Password string `json:"password"`
	Role     Role   `json:"role"`
}

type loginReq struct {
	Username string `json:"username"`
	Password string `json:"password"`
}

type loginResp struct {
	Token string     `json:"token"`
	User  PublicUser `json:"user"`
}

func (h *Handler) Register(c *fiber.Ctx) error {
	var req registerReq
	if err := c.BodyParser(&req); err != nil {
		return errResp(c, fiber.StatusBadRequest, "validation_failed", "invalid json")
	}
	u, err := h.svc.Register(c.UserContext(), req.Username, req.Password, req.Role)
	switch {
	case errors.Is(err, ErrUserExists):
		return errResp(c, fiber.StatusConflict, "user_exists", "username already taken")
	case errors.Is(err, ErrInvalidRole):
		return errResp(c, fiber.StatusBadRequest, "validation_failed", "invalid role")
	case errors.Is(err, ErrWeakPassword):
		return errResp(c, fiber.StatusBadRequest, "validation_failed", "password must be >= 8 chars")
	case errors.Is(err, ErrInvalidUsername):
		return errResp(c, fiber.StatusBadRequest, "validation_failed", "username must be >= 3 chars")
	case err != nil:
		return errResp(c, fiber.StatusInternalServerError, "internal", "register failed")
	}
	return c.Status(fiber.StatusCreated).JSON(okEnv(u))
}

func (h *Handler) Login(c *fiber.Ctx) error {
	var req loginReq
	if err := c.BodyParser(&req); err != nil {
		return errResp(c, fiber.StatusBadRequest, "validation_failed", "invalid json")
	}
	tok, u, err := h.svc.Login(c.UserContext(), req.Username, req.Password)
	if err != nil {
		if errors.Is(err, ErrInvalidCreds) {
			return errResp(c, fiber.StatusUnauthorized, "invalid_credentials", "invalid username or password")
		}
		return errResp(c, fiber.StatusInternalServerError, "internal", "login failed")
	}
	return c.JSON(okEnv(loginResp{Token: tok, User: u}))
}

func (h *Handler) Logout(c *fiber.Ctx) error {
	return c.JSON(okEnv(map[string]bool{"ok": true}))
}

func (h *Handler) Me(c *fiber.Ctx) error {
	cl, ok := ClaimsFromContext(c.UserContext())
	if !ok {
		return errResp(c, fiber.StatusUnauthorized, "unauthorized", "no auth context")
	}
	u, err := h.svc.Me(c.UserContext(), cl.UserID)
	if err != nil {
		return errResp(c, fiber.StatusNotFound, "not_found", "user not found")
	}
	return c.JSON(okEnv(u))
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
