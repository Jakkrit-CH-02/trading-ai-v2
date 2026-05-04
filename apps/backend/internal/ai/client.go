package ai

import (
	"bytes"
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"log/slog"
	"net/http"
	"sync"
	"time"
)

// ErrCircuitOpen is returned when the breaker is open.
var ErrCircuitOpen = errors.New("ai client: circuit open")

// InferenceRequest is sent to the AI inference service.
type InferenceRequest struct {
	Symbol   string             `json:"symbol"`
	Interval string             `json:"interval"`
	Features map[string]float64 `json:"features"`
}

// InferenceResponse is the AI service reply.
type InferenceResponse struct {
	Action       string  `json:"action"`        // "buy" | "sell" | "hold"
	Confidence   float64 `json:"confidence"`    // 0..1
	ModelVersion string  `json:"model_version"`
}

// Inferer is the minimum interface strategies need.
type Inferer interface {
	Infer(ctx context.Context, req InferenceRequest) (InferenceResponse, error)
}

// Config controls timeouts, retries and the breaker.
type Config struct {
	BaseURL          string
	Timeout          time.Duration
	MaxRetries       int
	RetryBackoff     time.Duration
	BreakerThreshold int           // consecutive failures to open
	BreakerCooldown  time.Duration // open → half-open delay
}

func (c *Config) defaults() {
	if c.Timeout <= 0 {
		c.Timeout = 2 * time.Second
	}
	if c.MaxRetries < 0 {
		c.MaxRetries = 0
	}
	if c.RetryBackoff <= 0 {
		c.RetryBackoff = 100 * time.Millisecond
	}
	if c.BreakerThreshold <= 0 {
		c.BreakerThreshold = 5
	}
	if c.BreakerCooldown <= 0 {
		c.BreakerCooldown = 30 * time.Second
	}
}

// Client is a small resilient HTTP client for the inference API.
type Client struct {
	cfg  Config
	http *http.Client
	cb   *breaker
	now  func() time.Time
}

func New(cfg Config) *Client {
	cfg.defaults()
	return &Client{
		cfg:  cfg,
		http: &http.Client{Timeout: cfg.Timeout},
		cb:   newBreaker(cfg.BreakerThreshold, cfg.BreakerCooldown, time.Now),
		now:  time.Now,
	}
}

func (c *Client) Infer(ctx context.Context, req InferenceRequest) (InferenceResponse, error) {
	if !c.cb.allow() {
		return InferenceResponse{}, ErrCircuitOpen
	}

	body, err := json.Marshal(req)
	if err != nil {
		return InferenceResponse{}, fmt.Errorf("ai client: marshal: %w", err)
	}

	url := c.cfg.BaseURL + "/v1/infer"
	var lastErr error
	for attempt := 0; attempt <= c.cfg.MaxRetries; attempt++ {
		if attempt > 0 {
			select {
			case <-ctx.Done():
				return InferenceResponse{}, ctx.Err()
			case <-time.After(c.cfg.RetryBackoff * time.Duration(attempt)):
			}
		}
		resp, err := c.do(ctx, url, body)
		if err == nil {
			c.cb.success()
			return resp, nil
		}
		lastErr = err
		slog.WarnContext(ctx, "ai inference attempt failed",
			"service", "ai",
			"attempt", attempt+1,
			"error", err.Error(),
		)
	}
	c.cb.failure()
	return InferenceResponse{}, fmt.Errorf("ai client: infer: %w", lastErr)
}

func (c *Client) do(ctx context.Context, url string, body []byte) (InferenceResponse, error) {
	httpReq, err := http.NewRequestWithContext(ctx, http.MethodPost, url, bytes.NewReader(body))
	if err != nil {
		return InferenceResponse{}, fmt.Errorf("build request: %w", err)
	}
	httpReq.Header.Set("Content-Type", "application/json")

	resp, err := c.http.Do(httpReq)
	if err != nil {
		return InferenceResponse{}, fmt.Errorf("http: %w", err)
	}
	defer resp.Body.Close()

	if resp.StatusCode >= 500 {
		return InferenceResponse{}, fmt.Errorf("upstream status %d", resp.StatusCode)
	}
	if resp.StatusCode >= 400 {
		// 4xx is a non-retriable client error; surface and break the loop
		// by counting it as a failure but reporting a sentinel-shaped error.
		raw, _ := io.ReadAll(resp.Body)
		return InferenceResponse{}, fmt.Errorf("client status %d: %s", resp.StatusCode, string(raw))
	}

	var out InferenceResponse
	if err := json.NewDecoder(resp.Body).Decode(&out); err != nil {
		return InferenceResponse{}, fmt.Errorf("decode: %w", err)
	}
	return out, nil
}

// breaker is a small consecutive-failure circuit breaker.
//
//	closed   → calls allowed; on N consecutive failures → open
//	open     → calls rejected until cooldown elapses → half-open
//	halfOpen → one trial call allowed; success → closed, failure → open
type breaker struct {
	mu          sync.Mutex
	threshold   int
	cooldown    time.Duration
	now         func() time.Time
	failures    int
	state       breakerState
	openedAt    time.Time
}

type breakerState int

const (
	stateClosed breakerState = iota
	stateOpen
	stateHalfOpen
)

func newBreaker(threshold int, cooldown time.Duration, now func() time.Time) *breaker {
	return &breaker{threshold: threshold, cooldown: cooldown, now: now, state: stateClosed}
}

func (b *breaker) allow() bool {
	b.mu.Lock()
	defer b.mu.Unlock()
	switch b.state {
	case stateClosed, stateHalfOpen:
		return true
	case stateOpen:
		if b.now().Sub(b.openedAt) >= b.cooldown {
			b.state = stateHalfOpen
			return true
		}
		return false
	}
	return false
}

func (b *breaker) success() {
	b.mu.Lock()
	defer b.mu.Unlock()
	b.failures = 0
	b.state = stateClosed
}

func (b *breaker) failure() {
	b.mu.Lock()
	defer b.mu.Unlock()
	b.failures++
	if b.state == stateHalfOpen || b.failures >= b.threshold {
		b.state = stateOpen
		b.openedAt = b.now()
	}
}
