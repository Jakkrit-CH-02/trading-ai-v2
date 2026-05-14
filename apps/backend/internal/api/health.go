package api

import (
	"bytes"
	"context"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"time"

	"github.com/gofiber/fiber/v2"
)

type depStatus string

const (
	depUp   depStatus = "up"
	depDown depStatus = "down"
)

type healthDeps struct {
	Postgres depStatus `json:"postgres"`
	Redis    depStatus `json:"redis"`
}

type healthBody struct {
	Status string     `json:"status"`
	Deps   healthDeps `json:"deps"`
}

func (s *Server) handleHealthz(c *fiber.Ctx) error {
	pingCtx, cancel := context.WithTimeout(c.UserContext(), 1*time.Second)
	defer cancel()

	body := healthBody{
		Status: "ok",
		Deps: healthDeps{
			Postgres: pingStatus(pingCtx, s.pg),
			Redis:    pingStatus(pingCtx, s.rdb),
		},
	}
	if body.Deps.Postgres == depDown || body.Deps.Redis == depDown {
		body.Status = "degraded"
	}
	return OK(c, body)
}

func pingStatus(ctx context.Context, p Pinger) depStatus {
	if p == nil {
		return depDown
	}
	if err := p.Ping(ctx); err != nil {
		return depDown
	}
	return depUp
}

func (s *Server) handleAIHealthz(c *fiber.Ctx) error {
	body, err := s.ai.fetchHealth(c.UserContext())
	if err != nil {
		return Err(c, fiber.StatusBadGateway, "upstream_unavailable", err.Error())
	}
	return OK(c, body)
}

type aiClient struct {
	baseURL string
	http    *http.Client
}

func newAIClient(baseURL string) *aiClient {
	return &aiClient{
		baseURL: baseURL,
		http:    &http.Client{Timeout: 2 * time.Second},
	}
}

func (cl *aiClient) fetchHealth(ctx context.Context) (json.RawMessage, error) {
	req, err := http.NewRequestWithContext(ctx, http.MethodGet, cl.baseURL+"/healthz", nil)
	if err != nil {
		return nil, err
	}
	resp, err := cl.http.Do(req)
	if err != nil {
		return nil, err
	}
	defer func() { _ = resp.Body.Close() }()

	raw, err := io.ReadAll(resp.Body)
	if err != nil {
		return nil, fmt.Errorf("ai health: read body: %w", err)
	}
	// Unwrap envelope if present so the backend re-wraps consistently.
	var env struct {
		Data  json.RawMessage `json:"data"`
		Error *APIError       `json:"error"`
	}
	if jerr := json.Unmarshal(raw, &env); jerr == nil && env.Data != nil {
		return env.Data, nil
	}
	return bytes.TrimSpace(raw), nil
}
