package binance

import (
	"context"
	"encoding/json"
	"fmt"
	"log/slog"
	"strings"
	"time"

	"github.com/gorilla/websocket"
	"github.com/jakkrit-ch/trading-ai-v2/backend/internal/domain"
	"github.com/shopspring/decimal"
)

// wsDialer is a package-level seam for tests to substitute the dialer.
var wsDialer = func(ctx context.Context, url string) (*websocket.Conn, error) {
	c, _, err := websocket.DefaultDialer.DialContext(ctx, url, nil)
	return c, err
}

type klineEvent struct {
	EventType string `json:"e"`
	EventTime int64  `json:"E"`
	Symbol    string `json:"s"`
	Kline     struct {
		StartTime  int64  `json:"t"`
		CloseTime  int64  `json:"T"`
		Symbol     string `json:"s"`
		Interval   string `json:"i"`
		Open       string `json:"o"`
		Close      string `json:"c"`
		High       string `json:"h"`
		Low        string `json:"l"`
		Volume     string `json:"v"`
		IsClosed   bool   `json:"x"`
	} `json:"k"`
}

// KlineStreamOptions tunes reconnect behavior.
type KlineStreamOptions struct {
	// OnlyClosed yields a bar only when the kline closes (default true).
	OnlyClosed bool
	// MinBackoff and MaxBackoff bound exponential reconnect delay.
	MinBackoff time.Duration
	MaxBackoff time.Duration
	// Logger is optional.
	Logger *slog.Logger
}

func (o *KlineStreamOptions) defaults() {
	if o.MinBackoff <= 0 {
		o.MinBackoff = 500 * time.Millisecond
	}
	if o.MaxBackoff <= 0 {
		o.MaxBackoff = 30 * time.Second
	}
	if o.Logger == nil {
		o.Logger = slog.Default()
	}
}

// KlineStream subscribes to <symbol>@kline_<interval> and returns a channel
// of decoded bars. Reconnect with exponential backoff is automatic until
// ctx is canceled, at which point the channel is closed.
func (c *Client) KlineStream(ctx context.Context, symbol domain.Symbol, interval string) <-chan domain.Bar {
	return c.KlineStreamWithOptions(ctx, symbol, interval, KlineStreamOptions{OnlyClosed: true})
}

// KlineStreamWithOptions is KlineStream with explicit options.
func (c *Client) KlineStreamWithOptions(ctx context.Context, symbol domain.Symbol, interval string, opts KlineStreamOptions) <-chan domain.Bar {
	opts.defaults()
	out := make(chan domain.Bar, 64)

	stream := strings.ToLower(string(symbol)) + "@kline_" + interval
	endpoint := c.wsURL + "/ws/" + stream

	go func() {
		defer close(out)
		backoff := opts.MinBackoff

		for {
			if ctx.Err() != nil {
				return
			}
			err := c.runKlineConn(ctx, endpoint, symbol, interval, opts, out)
			if ctx.Err() != nil {
				return
			}
			if err != nil {
				opts.Logger.WarnContext(ctx, "binance ws disconnected, reconnecting",
					"service", "binance",
					"symbol", string(symbol),
					"err", err.Error(),
					"backoff_ms", backoff.Milliseconds(),
				)
			}
			select {
			case <-ctx.Done():
				return
			case <-time.After(backoff):
			}
			backoff *= 2
			if backoff > opts.MaxBackoff {
				backoff = opts.MaxBackoff
			}
		}
	}()

	return out
}

func (c *Client) runKlineConn(ctx context.Context, endpoint string, sym domain.Symbol, interval string, opts KlineStreamOptions, out chan<- domain.Bar) error {
	conn, err := wsDialer(ctx, endpoint)
	if err != nil {
		return fmt.Errorf("dial: %w", err)
	}
	defer conn.Close()

	// Push reads forward in a goroutine so we can honor ctx promptly.
	readErr := make(chan error, 1)
	go func() {
		for {
			_, raw, err := conn.ReadMessage()
			if err != nil {
				readErr <- err
				return
			}
			var ev klineEvent
			if err := json.Unmarshal(raw, &ev); err != nil {
				continue
			}
			if opts.OnlyClosed && !ev.Kline.IsClosed {
				continue
			}
			bar, err := klineToBar(sym, interval, ev)
			if err != nil {
				continue
			}
			select {
			case <-ctx.Done():
				readErr <- ctx.Err()
				return
			case out <- bar:
			}
		}
	}()

	select {
	case <-ctx.Done():
		_ = conn.Close()
		return ctx.Err()
	case err := <-readErr:
		return err
	}
}

func klineToBar(sym domain.Symbol, interval string, ev klineEvent) (domain.Bar, error) {
	open, err := decimal.NewFromString(ev.Kline.Open)
	if err != nil {
		return domain.Bar{}, err
	}
	high, err := decimal.NewFromString(ev.Kline.High)
	if err != nil {
		return domain.Bar{}, err
	}
	low, err := decimal.NewFromString(ev.Kline.Low)
	if err != nil {
		return domain.Bar{}, err
	}
	cls, err := decimal.NewFromString(ev.Kline.Close)
	if err != nil {
		return domain.Bar{}, err
	}
	vol, err := decimal.NewFromString(ev.Kline.Volume)
	if err != nil {
		return domain.Bar{}, err
	}
	return domain.Bar{
		Symbol:    sym,
		Interval:  interval,
		OpenTime:  ev.Kline.StartTime,
		CloseTime: ev.Kline.CloseTime,
		Open:      open,
		High:      high,
		Low:       low,
		Close:     cls,
		Volume:    vol,
	}, nil
}
