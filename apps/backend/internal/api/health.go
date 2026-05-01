package api

import (
	"context"
	"encoding/json"
	"net/http"
	"time"
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

func (s *Server) handleHealthz(w http.ResponseWriter, r *http.Request) {
	pingCtx, cancel := context.WithTimeout(r.Context(), 1*time.Second)
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
	WriteJSON(w, http.StatusOK, body)
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

func (s *Server) handleAIHealthz(w http.ResponseWriter, r *http.Request) {
	body, err := s.ai.fetchHealth(r.Context())
	if err != nil {
		WriteError(w, http.StatusBadGateway, "upstream_unavailable", err.Error())
		return
	}
	WriteJSON(w, http.StatusOK, body)
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

func (c *aiClient) fetchHealth(ctx context.Context) (json.RawMessage, error) {
	req, err := http.NewRequestWithContext(ctx, http.MethodGet, c.baseURL+"/healthz", nil)
	if err != nil {
		return nil, err
	}
	resp, err := c.http.Do(req)
	if err != nil {
		return nil, err
	}
	defer func() { _ = resp.Body.Close() }()

	var raw json.RawMessage
	if err := json.NewDecoder(resp.Body).Decode(&raw); err != nil {
		return nil, err
	}
	// AI service returns the envelope itself; unwrap to the inner data so the
	// backend handler can re-wrap consistently.
	var env struct {
		Data  json.RawMessage `json:"data"`
		Error *APIError       `json:"error"`
	}
	if jerr := json.Unmarshal(raw, &env); jerr == nil && env.Data != nil {
		return env.Data, nil
	}
	return raw, nil
}
