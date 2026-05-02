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

	"github.com/go-chi/chi/v5"
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
	a.proxy(w, r, http.MethodPost, "/api/datasets/build")
}

// ComputeFeatures proxies POST /api/ai/features/compute to ai-service /api/features/compute.
func (a *AI) ComputeFeatures(w http.ResponseWriter, r *http.Request) {
	a.proxy(w, r, http.MethodPost, "/api/features/compute")
}

// RunTraining proxies POST /api/ai/training/run.
func (a *AI) RunTraining(w http.ResponseWriter, r *http.Request) {
	a.proxy(w, r, http.MethodPost, "/api/training/run")
}

// GetTrainingJob proxies GET /api/ai/training/{id}.
func (a *AI) GetTrainingJob(w http.ResponseWriter, r *http.Request) {
	id := chi.URLParam(r, "id")
	a.proxy(w, r, http.MethodGet, "/api/training/"+id)
}

// ListModels proxies GET /api/ai/models.
func (a *AI) ListModels(w http.ResponseWriter, r *http.Request) {
	a.proxy(w, r, http.MethodGet, "/api/models")
}

// PromoteModel proxies POST /api/ai/models/{id}/promote.
func (a *AI) PromoteModel(w http.ResponseWriter, r *http.Request) {
	id := chi.URLParam(r, "id")
	a.proxy(w, r, http.MethodPost, "/api/models/"+id+"/promote")
}

// Predict proxies POST /api/ai/predict (forwarding the ?explain= query).
func (a *AI) Predict(w http.ResponseWriter, r *http.Request) {
	path := "/api/predict"
	if q := r.URL.RawQuery; q != "" {
		path += "?" + q
	}
	a.proxy(w, r, http.MethodPost, path)
}

// ReloadModel proxies POST /api/ai/predict/reload.
func (a *AI) ReloadModel(w http.ResponseWriter, r *http.Request) {
	a.proxy(w, r, http.MethodPost, "/api/predict/reload")
}

func (a *AI) proxy(w http.ResponseWriter, r *http.Request, method, path string) {
	var body []byte
	if r.Body != nil && method != http.MethodGet {
		b, err := io.ReadAll(r.Body)
		if err != nil {
			writeProxyError(w, http.StatusBadRequest, "validation_failed", err.Error())
			return
		}
		body = b
		defer func() { _ = r.Body.Close() }()
	}

	upstream, err := a.forward(r.Context(), method, path, body)
	if err != nil {
		writeProxyError(w, http.StatusBadGateway, "upstream_unavailable", err.Error())
		return
	}
	defer func() { _ = upstream.Body.Close() }()

	w.Header().Set("Content-Type", "application/json; charset=utf-8")
	w.WriteHeader(upstream.StatusCode)
	if _, err := io.Copy(w, upstream.Body); err != nil {
		return
	}
}

func (a *AI) forward(ctx context.Context, method, path string, body []byte) (*http.Response, error) {
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
	if body != nil {
		req.Header.Set("Content-Type", "application/json")
	}
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
