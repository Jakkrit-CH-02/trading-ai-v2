package binance

import (
	"context"
	"crypto/hmac"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"net/http"
	"net/url"
	"strconv"
	"strings"
	"sync/atomic"
	"time"

	"github.com/jakkrit-ch/trading-ai-v2/backend/internal/domain"
	"github.com/shopspring/decimal"
)

// Client is a thin Binance REST + WS client.
//
// All public REST helpers honor ctx and the rate limiter. Signed endpoints
// require APIKey/APISecret to be set.
type Client struct {
	cfg        Config
	restURL    string
	wsURL      string
	http       *http.Client
	rl         *TokenBucket
	timeOffset atomic.Int64 // serverTime - localTime in ms
}

// New constructs a Client. The HTTP client defaults to a 10s timeout.
func New(cfg Config) *Client {
	if cfg.RecvWindow == 0 {
		cfg.RecvWindow = 5000
	}
	rest := cfg.RestBaseURL
	if rest == "" {
		if cfg.Testnet {
			rest = testnetREST
		} else {
			rest = mainnetREST
		}
	}
	ws := cfg.WSBaseURL
	if ws == "" {
		if cfg.Testnet {
			ws = testnetWS
		} else {
			ws = mainnetWS
		}
	}
	return &Client{
		cfg:     cfg,
		restURL: strings.TrimRight(rest, "/"),
		wsURL:   strings.TrimRight(ws, "/"),
		http:    &http.Client{Timeout: 10 * time.Second},
		// 1200 weight/min ≈ 20/sec; capacity=1200 to absorb bursts.
		rl: NewTokenBucket(1200, 20),
	}
}

// SetHTTPClient overrides the underlying *http.Client (used in tests).
func (c *Client) SetHTTPClient(h *http.Client) { c.http = h }

// SetRateLimiter overrides the limiter (tests).
func (c *Client) SetRateLimiter(rl *TokenBucket) { c.rl = rl }

// TimeOffsetMs returns serverTime - localTime, populated by SyncTime.
func (c *Client) TimeOffsetMs() int64 { return c.timeOffset.Load() }

// SyncTime queries GET /api/v3/time and stores the offset for signed requests.
func (c *Client) SyncTime(ctx context.Context) error {
	var out struct {
		ServerTime int64 `json:"serverTime"`
	}
	if err := c.do(ctx, http.MethodGet, "/api/v3/time", nil, false, 1, &out); err != nil {
		return fmt.Errorf("binance: sync time: %w", err)
	}
	local := time.Now().UTC().UnixMilli()
	c.timeOffset.Store(out.ServerTime - local)
	return nil
}

// GetExchangeInfo: GET /api/v3/exchangeInfo
func (c *Client) GetExchangeInfo(ctx context.Context) (*ExchangeInfo, error) {
	var out ExchangeInfo
	if err := c.do(ctx, http.MethodGet, "/api/v3/exchangeInfo", nil, false, 10, &out); err != nil {
		return nil, fmt.Errorf("binance: exchange info: %w", err)
	}
	return &out, nil
}

// GetAccount: GET /api/v3/account (signed).
func (c *Client) GetAccount(ctx context.Context) (*AccountInfo, error) {
	var out AccountInfo
	if err := c.do(ctx, http.MethodGet, "/api/v3/account", url.Values{}, true, 10, &out); err != nil {
		return nil, fmt.Errorf("binance: account: %w", err)
	}
	return &out, nil
}

// PlaceOrder: POST /api/v3/order (signed).
func (c *Client) PlaceOrder(ctx context.Context, req OrderRequest) (*OrderResponse, error) {
	q := url.Values{}
	q.Set("symbol", req.Symbol)
	q.Set("side", req.Side)
	q.Set("type", req.Type)
	if !req.Quantity.IsZero() {
		q.Set("quantity", req.Quantity.String())
	}
	if !req.Price.IsZero() {
		q.Set("price", req.Price.String())
	}
	if !req.StopPrice.IsZero() {
		q.Set("stopPrice", req.StopPrice.String())
	}
	if req.TimeInForce != "" {
		q.Set("timeInForce", req.TimeInForce)
	}
	if req.NewClientID != "" {
		q.Set("newClientOrderId", req.NewClientID)
	}
	var out OrderResponse
	if err := c.do(ctx, http.MethodPost, "/api/v3/order", q, true, 1, &out); err != nil {
		return nil, fmt.Errorf("binance: place order: %w", err)
	}
	return &out, nil
}

// CancelAllOpenOrders: DELETE /api/v3/openOrders?symbol=XYZ (signed).
// Returns the list of canceled orders. A 200 with an empty array means
// there were no open orders for the symbol.
func (c *Client) CancelAllOpenOrders(ctx context.Context, symbol string) ([]OrderResponse, error) {
	if symbol == "" {
		return nil, errors.New("binance: cancel all: symbol required")
	}
	q := url.Values{}
	q.Set("symbol", symbol)
	var out []OrderResponse
	if err := c.do(ctx, http.MethodDelete, "/api/v3/openOrders", q, true, 1, &out); err != nil {
		return nil, fmt.Errorf("binance: cancel all open orders: %w", err)
	}
	return out, nil
}

// CancelOrder: DELETE /api/v3/order (signed).
func (c *Client) CancelOrder(ctx context.Context, req CancelRequest) (*OrderResponse, error) {
	q := url.Values{}
	q.Set("symbol", req.Symbol)
	if req.OrderID != 0 {
		q.Set("orderId", strconv.FormatInt(req.OrderID, 10))
	}
	if req.OrigClientOrderID != "" {
		q.Set("origClientOrderId", req.OrigClientOrderID)
	}
	var out OrderResponse
	if err := c.do(ctx, http.MethodDelete, "/api/v3/order", q, true, 1, &out); err != nil {
		return nil, fmt.Errorf("binance: cancel order: %w", err)
	}
	return &out, nil
}

// GetKlines: GET /api/v3/klines. Returns bars normalized to domain.Bar.
func (c *Client) GetKlines(ctx context.Context, q KlinesQuery) ([]domain.Bar, error) {
	if q.Symbol == "" || q.Interval == "" {
		return nil, errors.New("binance: klines: symbol and interval required")
	}
	v := url.Values{}
	v.Set("symbol", q.Symbol)
	v.Set("interval", q.Interval)
	if q.StartMs > 0 {
		v.Set("startTime", strconv.FormatInt(q.StartMs, 10))
	}
	if q.EndMs > 0 {
		v.Set("endTime", strconv.FormatInt(q.EndMs, 10))
	}
	if q.Limit > 0 {
		v.Set("limit", strconv.Itoa(q.Limit))
	}

	// Klines come back as a [][]any with mixed numeric/string types.
	var raw [][]any
	if err := c.do(ctx, http.MethodGet, "/api/v3/klines?"+v.Encode(), nil, false, 1, &raw); err != nil {
		return nil, fmt.Errorf("binance: klines: %w", err)
	}
	bars := make([]domain.Bar, 0, len(raw))
	for _, r := range raw {
		if len(r) < 7 {
			continue
		}
		bar, err := parseKline(domain.Symbol(q.Symbol), q.Interval, r)
		if err != nil {
			return nil, fmt.Errorf("binance: klines: parse: %w", err)
		}
		bars = append(bars, bar)
	}
	return bars, nil
}

func parseKline(sym domain.Symbol, interval string, r []any) (domain.Bar, error) {
	openMs, ok1 := toInt64(r[0])
	closeMs, ok2 := toInt64(r[6])
	if !ok1 || !ok2 {
		return domain.Bar{}, fmt.Errorf("invalid time fields")
	}
	open, err := toDecimal(r[1])
	if err != nil {
		return domain.Bar{}, err
	}
	high, err := toDecimal(r[2])
	if err != nil {
		return domain.Bar{}, err
	}
	low, err := toDecimal(r[3])
	if err != nil {
		return domain.Bar{}, err
	}
	cls, err := toDecimal(r[4])
	if err != nil {
		return domain.Bar{}, err
	}
	vol, err := toDecimal(r[5])
	if err != nil {
		return domain.Bar{}, err
	}
	return domain.Bar{
		Symbol:    sym,
		Interval:  interval,
		OpenTime:  openMs,
		CloseTime: closeMs,
		Open:      open,
		High:      high,
		Low:       low,
		Close:     cls,
		Volume:    vol,
	}, nil
}

func toInt64(v any) (int64, bool) {
	switch x := v.(type) {
	case float64:
		return int64(x), true
	case int64:
		return x, true
	case json.Number:
		i, err := x.Int64()
		return i, err == nil
	}
	return 0, false
}

func toDecimal(v any) (decimal.Decimal, error) {
	switch x := v.(type) {
	case string:
		return decimal.NewFromString(x)
	case float64:
		return decimal.NewFromFloat(x), nil
	case json.Number:
		return decimal.NewFromString(x.String())
	}
	return decimal.Zero, fmt.Errorf("unexpected numeric type %T", v)
}

// do executes a request with rate limit + auth + retry on 429/5xx.
func (c *Client) do(ctx context.Context, method, path string, form url.Values, signed bool, weight float64, out any) error {
	if c.rl != nil {
		if err := c.rl.Wait(ctx, weight); err != nil {
			return err
		}
	}

	const maxAttempts = 3
	var lastErr error
	for attempt := 0; attempt < maxAttempts; attempt++ {
		if attempt > 0 {
			backoff := time.Duration(1<<attempt) * 200 * time.Millisecond
			select {
			case <-ctx.Done():
				return ctx.Err()
			case <-time.After(backoff):
			}
		}

		req, err := c.buildRequest(ctx, method, path, form, signed)
		if err != nil {
			return err
		}
		resp, err := c.http.Do(req)
		if err != nil {
			lastErr = err
			continue
		}
		body, _ := io.ReadAll(resp.Body)
		_ = resp.Body.Close()

		if resp.StatusCode == http.StatusTooManyRequests || resp.StatusCode >= 500 {
			lastErr = parseAPIError(resp.StatusCode, body)
			continue
		}
		if resp.StatusCode >= 400 {
			return parseAPIError(resp.StatusCode, body)
		}
		if out == nil || len(body) == 0 {
			return nil
		}
		if err := json.Unmarshal(body, out); err != nil {
			return fmt.Errorf("decode: %w", err)
		}
		return nil
	}
	return lastErr
}

func (c *Client) buildRequest(ctx context.Context, method, path string, form url.Values, signed bool) (*http.Request, error) {
	u := c.restURL + path

	var body io.Reader
	if signed {
		if c.cfg.APIKey == "" || c.cfg.APISecret == "" {
			return nil, errors.New("binance: signed request requires api key + secret")
		}
		if form == nil {
			form = url.Values{}
		}
		ts := time.Now().UTC().UnixMilli() + c.timeOffset.Load()
		form.Set("timestamp", strconv.FormatInt(ts, 10))
		form.Set("recvWindow", strconv.FormatInt(c.cfg.RecvWindow, 10))
		sig := sign(c.cfg.APISecret, form.Encode())
		form.Set("signature", sig)

		switch method {
		case http.MethodGet, http.MethodDelete:
			if strings.Contains(u, "?") {
				u += "&" + form.Encode()
			} else {
				u += "?" + form.Encode()
			}
		default:
			body = strings.NewReader(form.Encode())
		}
	} else if form != nil && method == http.MethodGet {
		if strings.Contains(u, "?") {
			u += "&" + form.Encode()
		} else {
			u += "?" + form.Encode()
		}
	}

	req, err := http.NewRequestWithContext(ctx, method, u, body)
	if err != nil {
		return nil, err
	}
	if signed || c.cfg.APIKey != "" {
		req.Header.Set("X-MBX-APIKEY", c.cfg.APIKey)
	}
	if body != nil {
		req.Header.Set("Content-Type", "application/x-www-form-urlencoded")
	}
	return req, nil
}

func sign(secret, payload string) string {
	mac := hmac.New(sha256.New, []byte(secret))
	mac.Write([]byte(payload))
	return hex.EncodeToString(mac.Sum(nil))
}

func parseAPIError(status int, body []byte) error {
	apiErr := &APIError{HTTPStatus: status}
	if len(body) > 0 {
		_ = json.Unmarshal(body, apiErr)
	}
	if apiErr.Msg == "" {
		apiErr.Msg = fmt.Sprintf("http %d: %s", status, string(body))
	}
	return apiErr
}
