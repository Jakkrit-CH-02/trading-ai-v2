// Package handlers carries thin HTTP handlers that compose internal services
// or proxy to sibling services. AI handlers forward requests to the Python
// ai-service so the frontend has a single backend to talk to.
package handlers

import (
	"bytes"
	"context"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"time"
)

type AI struct {
	baseURL string
	http    *http.Client
}

func NewAI(baseURL string) *AI {
	return &AI{
		baseURL: baseURL,
		http:    &http.Client{Timeout: 60 * time.Second},
	}
}

// BuildDataset proxies POST /api/ai/datasets/build to ai-service /api/datasets/build.
func (a *AI) BuildDataset(w http.ResponseWriter, r *http.Request) {
	a.proxy(w, r, "/api/datasets/build")
}

// ComputeFeatures proxies POST /api/ai/features/compute to ai-service /api/features/compute.
func (a *AI) ComputeFeatures(w http.ResponseWriter, r *http.Request) {
	a.proxy(w, r, "/api/features/compute")
}

func (a *AI) proxy(w http.ResponseWriter, r *http.Request, path string) {
	body, err := io.ReadAll(r.Body)
	if err != nil {
		writeProxyError(w, http.StatusBadRequest, "validation_failed", err.Error())
		return
	}
	defer func() { _ = r.Body.Close() }()

	upstream, err := a.forward(r.Context(), path, body)
	if err != nil {
		writeProxyError(w, http.StatusBadGateway, "upstream_unavailable", err.Error())
		return
	}
	defer func() { _ = upstream.Body.Close() }()

	w.Header().Set("Content-Type", "application/json; charset=utf-8")
	w.WriteHeader(upstream.StatusCode)
	if _, err := io.Copy(w, upstream.Body); err != nil {
		// Headers are already flushed; nothing useful to recover.
		return
	}
}

func (a *AI) forward(ctx context.Context, path string, body []byte) (*http.Response, error) {
	req, err := http.NewRequestWithContext(ctx, http.MethodPost, a.baseURL+path, bytes.NewReader(body))
	if err != nil {
		return nil, fmt.Errorf("ai proxy: build request: %w", err)
	}
	req.Header.Set("Content-Type", "application/json")
	resp, err := a.http.Do(req)
	if err != nil {
		return nil, fmt.Errorf("ai proxy: %s: %w", path, err)
	}
	return resp, nil
}

func writeProxyError(w http.ResponseWriter, status int, code, msg string) {
	w.Header().Set("Content-Type", "application/json; charset=utf-8")
	w.WriteHeader(status)
	_ = json.NewEncoder(w).Encode(map[string]any{
		"data": nil,
		"error": map[string]any{
			"code":    code,
			"message": msg,
		},
	})
}
