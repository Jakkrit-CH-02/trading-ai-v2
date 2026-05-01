package binance

import (
	"context"
	"net/http"
	"net/http/httptest"
	"strings"
	"sync/atomic"
	"testing"
	"time"

	"github.com/gorilla/websocket"
	"github.com/jakkrit-ch/trading-ai-v2/backend/internal/domain"
	"github.com/stretchr/testify/require"
)

const klineFrameClosed = `{"e":"kline","E":1700000059999,"s":"BTCUSDT","k":{"t":1700000000000,"T":1700000059999,"s":"BTCUSDT","i":"1m","o":"100.0","c":"105.0","h":"110.0","l":"90.0","v":"12.5","x":true}}`

func startWSServer(t *testing.T, handler func(c *websocket.Conn)) *httptest.Server {
	t.Helper()
	up := websocket.Upgrader{CheckOrigin: func(r *http.Request) bool { return true }}
	return httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		conn, err := up.Upgrade(w, r, nil)
		if err != nil {
			t.Logf("upgrade failed: %v", err)
			return
		}
		defer conn.Close()
		handler(conn)
	}))
}

// httptest URLs are http://; rewrite to ws:// for the dialer.
func wsURLFromHTTP(httpURL string) string {
	return strings.Replace(httpURL, "http://", "ws://", 1)
}

func TestKlineStream_ReceivesBar(t *testing.T) {
	srv := startWSServer(t, func(c *websocket.Conn) {
		_ = c.WriteMessage(websocket.TextMessage, []byte(klineFrameClosed))
		// keep open until client disconnects
		_, _, _ = c.ReadMessage()
	})
	defer srv.Close()

	cli := New(Config{WSBaseURL: wsURLFromHTTP(srv.URL)})

	ctx, cancel := context.WithTimeout(context.Background(), 2*time.Second)
	defer cancel()

	ch := cli.KlineStream(ctx, domain.Symbol("BTCUSDT"), "1m")
	select {
	case bar, ok := <-ch:
		require.True(t, ok)
		require.Equal(t, domain.Symbol("BTCUSDT"), bar.Symbol)
		require.Equal(t, "1m", bar.Interval)
		require.Equal(t, int64(1700000000000), bar.OpenTime)
	case <-ctx.Done():
		t.Fatal("did not receive bar before timeout")
	}
}

func TestKlineStream_FiltersUnclosedByDefault(t *testing.T) {
	openFrame := strings.Replace(klineFrameClosed, `"x":true`, `"x":false`, 1)
	srv := startWSServer(t, func(c *websocket.Conn) {
		_ = c.WriteMessage(websocket.TextMessage, []byte(openFrame))
		_ = c.WriteMessage(websocket.TextMessage, []byte(klineFrameClosed))
		_, _, _ = c.ReadMessage()
	})
	defer srv.Close()

	cli := New(Config{WSBaseURL: wsURLFromHTTP(srv.URL)})
	ctx, cancel := context.WithTimeout(context.Background(), 2*time.Second)
	defer cancel()

	ch := cli.KlineStream(ctx, domain.Symbol("BTCUSDT"), "1m")
	select {
	case bar := <-ch:
		// First emitted bar must be the closed one (open one was filtered).
		require.Equal(t, int64(1700000059999), bar.CloseTime)
	case <-ctx.Done():
		t.Fatal("timed out")
	}
}

func TestKlineStream_ReconnectsOnDrop(t *testing.T) {
	var connCount atomic.Int32
	srv := startWSServer(t, func(c *websocket.Conn) {
		n := connCount.Add(1)
		_ = c.WriteMessage(websocket.TextMessage, []byte(klineFrameClosed))
		if n == 1 {
			// Forcibly drop the first connection to trigger reconnect.
			_ = c.Close()
			return
		}
		// Subsequent connections stay open until ctx cancels via client close.
		_, _, _ = c.ReadMessage()
	})
	defer srv.Close()

	cli := New(Config{WSBaseURL: wsURLFromHTTP(srv.URL)})
	ctx, cancel := context.WithTimeout(context.Background(), 3*time.Second)
	defer cancel()

	ch := cli.KlineStreamWithOptions(ctx, domain.Symbol("BTCUSDT"), "1m", KlineStreamOptions{
		OnlyClosed: true,
		MinBackoff: 50 * time.Millisecond,
		MaxBackoff: 200 * time.Millisecond,
	})

	// Expect at least two bars from two distinct connections.
	got := 0
	deadline := time.After(2500 * time.Millisecond)
	for got < 2 {
		select {
		case _, ok := <-ch:
			if !ok {
				t.Fatalf("channel closed early; got %d bars", got)
			}
			got++
		case <-deadline:
			t.Fatalf("only %d bars, conn=%d", got, connCount.Load())
		}
	}
	require.GreaterOrEqual(t, connCount.Load(), int32(2), "expected at least 2 connections (reconnect)")
}

func TestKlineStream_ChannelClosedOnCtxCancel(t *testing.T) {
	srv := startWSServer(t, func(c *websocket.Conn) {
		_, _, _ = c.ReadMessage()
	})
	defer srv.Close()

	cli := New(Config{WSBaseURL: wsURLFromHTTP(srv.URL)})
	ctx, cancel := context.WithCancel(context.Background())
	ch := cli.KlineStream(ctx, domain.Symbol("BTCUSDT"), "1m")

	time.Sleep(100 * time.Millisecond)
	cancel()

	select {
	case _, ok := <-ch:
		require.False(t, ok, "channel should be closed after ctx cancel")
	case <-time.After(2 * time.Second):
		t.Fatal("channel was not closed after ctx cancel")
	}
}
