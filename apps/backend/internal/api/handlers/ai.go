// Package handlers carries thin HTTP handlers that compose internal services
// or proxy to sibling services. AI handlers forward requests to the Python
// ai-service so the frontend has a single backend to talk to.
package handlers

import (
	"bytes"
	"context"
	"fmt"
	"io"
	"net/http"
	"time"

	"github.com/gofiber/fiber/v2"
)

type aiProxy struct {
	baseURL string
	http    *http.Client
}

func newAIProxy(baseURL string) *aiProxy {
	return &aiProxy{
		baseURL: baseURL,
		http:    &http.Client{Timeout: 60 * time.Second},
	}
}

func (a *aiProxy) buildDataset(c *fiber.Ctx) error {
	return a.proxy(c, http.MethodPost, "/api/datasets/build")
}

func (a *aiProxy) computeFeatures(c *fiber.Ctx) error {
	return a.proxy(c, http.MethodPost, "/api/features/compute")
}

func (a *aiProxy) runTraining(c *fiber.Ctx) error {
	return a.proxy(c, http.MethodPost, "/api/training/run")
}

func (a *aiProxy) getTrainingJob(c *fiber.Ctx) error {
	id := c.Params("id")
	return a.proxy(c, http.MethodGet, "/api/training/"+id)
}

func (a *aiProxy) listModels(c *fiber.Ctx) error {
	return a.proxy(c, http.MethodGet, "/api/models")
}

func (a *aiProxy) promoteModel(c *fiber.Ctx) error {
	id := c.Params("id")
	return a.proxy(c, http.MethodPost, "/api/models/"+id+"/promote")
}

func (a *aiProxy) predict(c *fiber.Ctx) error {
	path := "/api/predict"
	if q := string(c.Request().URI().QueryString()); q != "" {
		path += "?" + q
	}
	return a.proxy(c, http.MethodPost, path)
}

func (a *aiProxy) reloadModel(c *fiber.Ctx) error {
	return a.proxy(c, http.MethodPost, "/api/predict/reload")
}

func (a *aiProxy) proxy(c *fiber.Ctx, method, path string) error {
	var body []byte
	if method != http.MethodGet {
		body = c.Body()
	}

	upstream, err := a.forward(c.UserContext(), method, path, body)
	if err != nil {
		return writeError(c, fiber.StatusBadGateway, "upstream_unavailable", err.Error())
	}
	defer func() { _ = upstream.Body.Close() }()

	respBody, err := io.ReadAll(upstream.Body)
	if err != nil {
		return writeError(c, fiber.StatusBadGateway, "upstream_unavailable", "failed to read upstream response")
	}
	c.Set("Content-Type", "application/json; charset=utf-8")
	return c.Status(upstream.StatusCode).Send(respBody)
}

func (a *aiProxy) forward(ctx context.Context, method, path string, body []byte) (*http.Response, error) {
	var reader *bytes.Reader
	if body != nil {
		reader = bytes.NewReader(body)
	} else {
		reader = bytes.NewReader(nil)
	}
	req, err := http.NewRequestWithContext(ctx, method, a.baseURL+path, reader)
	if err != nil {
		return nil, fmt.Errorf("ai proxy: build request: %w", err)
	}
	if len(body) > 0 {
		req.Header.Set("Content-Type", "application/json")
	}
	resp, err := a.http.Do(req)
	if err != nil {
		return nil, fmt.Errorf("ai proxy: %s: %w", path, err)
	}
	return resp, nil
}
