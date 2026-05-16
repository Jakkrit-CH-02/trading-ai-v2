package handlers

import (
	"bufio"
	"log/slog"
	"net"
	"net/http"
	"sync"
	"time"

	"github.com/gofiber/fiber/v2"
	"github.com/gorilla/websocket"
	"github.com/valyala/fasthttp"

	"github.com/jakkrit-ch/trading-ai-v2/backend/internal/data/market"
)

// marketWS handles the /api/market/stream WebSocket endpoint.
type marketWS struct {
	hub      *market.Hub
	upgrader websocket.Upgrader
}

func newMarketWS(hub *market.Hub) *marketWS {
	return &marketWS{
		hub: hub,
		upgrader: websocket.Upgrader{
			// Allow all origins; JWT auth is handled at the Fiber middleware layer.
			CheckOrigin: func(r *http.Request) bool { return true },
		},
	}
}

// wsSubscribeMsg is the first frame the client must send after connecting.
type wsSubscribeMsg struct {
	Type    string   `json:"type"`
	Symbols []string `json:"symbols"`
}

// wsBarMsg is pushed to the client for every incoming bar.
type wsBarMsg struct {
	Type   string `json:"type"`
	Symbol string `json:"symbol"`
	Bar    barDTO `json:"bar"`
}

// stream upgrades the HTTP connection to WebSocket and streams live bar events.
//
// Protocol:
//  1. Client sends: {"type":"subscribe","symbols":["BTCUSDT","ETHUSDT"]}
//  2. Server streams: {"type":"bar","symbol":"BTCUSDT","bar":{…}} for each bar
func (h *marketWS) stream(c *fiber.Ctx) error {
	fctx := c.Context()

	// Build a minimal *http.Request so gorilla's upgrader can inspect WS headers.
	req, err := buildHTTPRequest(fctx)
	if err != nil {
		return writeError(c, fiber.StatusBadRequest, "ws_upgrade_failed", err.Error())
	}

	// hijackCh delivers the raw net.Conn once fasthttp hands it off.
	hijackCh := make(chan net.Conn, 1)
	// connDone is closed by handleConn when the WS session ends, which unblocks
	// the Hijack callback so fasthttp can reclaim the goroutine.
	connDone := make(chan struct{})

	// Tell fasthttp not to write a response and to yield the connection.
	fctx.HijackSetNoResponse(true)
	fctx.Hijack(func(conn net.Conn) {
		hijackCh <- conn
		// Wait until the WS session is over before returning, so fasthttp does
		// not close or reuse the connection while we still own it.
		<-connDone
	})

	// Drive the WebSocket upgrade and message loop off the Fiber handler
	// goroutine so we don't block the server's connection processing.
	go func() {
		conn := <-hijackCh
		defer close(connDone)
		h.handleConn(conn, req)
	}()

	return nil
}

// handleConn completes the WebSocket upgrade and runs the message loop.
func (h *marketWS) handleConn(conn net.Conn, req *http.Request) {
	rw := newFakeResponseWriter(conn)
	wsConn, err := h.upgrader.Upgrade(rw, req, nil)
	if err != nil {
		slog.Warn("market ws: upgrade failed", "service", "api", "err", err)
		conn.Close()
		return
	}
	defer wsConn.Close()

	// Expect the subscribe message as the very first frame.
	// Give the client 10 s to send the subscribe message before timing out.
	wsConn.SetReadDeadline(time.Now().Add(10 * time.Second))
	var sub wsSubscribeMsg
	if err := wsConn.ReadJSON(&sub); err != nil {
		slog.Warn("market ws: subscribe read failed", "service", "api", "err", err)
		return
	}
	wsConn.SetReadDeadline(time.Time{})

	if sub.Type != "subscribe" || len(sub.Symbols) == 0 {
		_ = wsConn.WriteJSON(map[string]string{
			"type":    "error",
			"message": "expected subscribe message with at least one symbol",
		})
		return
	}

	const maxWsSymbols = 20
	if len(sub.Symbols) > maxWsSymbols {
		slog.Warn("market ws: invalid symbol count", "service", "api", "count", len(sub.Symbols))
		_ = wsConn.WriteJSON(map[string]string{
			"type":    "error",
			"message": "too many symbols: max 20",
		})
		return
	}

	// shutdown is closed when any goroutine detects the connection is gone.
	var once sync.Once
	shutdown := make(chan struct{})
	closeFn := func() { once.Do(func() { close(shutdown) }) }
	defer closeFn()

	// Read pump: drives gorilla control-frame handling and detects disconnects.
	// A 60 s read deadline is refreshed on every pong; if no pong arrives within
	// 60 s the read will time out and closeFn() will fire.
	wsConn.SetReadDeadline(time.Now().Add(60 * time.Second))
	wsConn.SetPongHandler(func(string) error {
		wsConn.SetReadDeadline(time.Now().Add(60 * time.Second))
		return nil
	})
	go func() {
		defer closeFn()
		for {
			if _, _, err := wsConn.NextReader(); err != nil {
				return
			}
		}
	}()

	// Ping ticker: sends a ping every 30 s to keep the connection alive and
	// detect dead clients (no pong → 60 s read deadline fires in read pump).
	go func() {
		t := time.NewTicker(30 * time.Second)
		defer t.Stop()
		for {
			select {
			case <-shutdown:
				return
			case <-t.C:
				if err := wsConn.WriteControl(websocket.PingMessage, nil, time.Now().Add(5*time.Second)); err != nil {
					closeFn()
					return
				}
			}
		}
	}()

	// mergedBars collects bars from all subscribed symbols into a single channel.
	type barEvent struct {
		symbol string
		bar    barDTO
	}
	mergedBars := make(chan barEvent, 64)

	// Launch one goroutine per symbol that forwards bars into mergedBars.
	for _, sym := range sub.Symbols {
		ch := h.hub.Subscribe(sym)
		go func(symbol string) {
			defer h.hub.Unsubscribe(symbol, ch)
			for {
				select {
				case <-shutdown:
					return
				case bar, ok := <-ch:
					if !ok {
						return
					}
					ev := barEvent{symbol: symbol, bar: toBarDTO(bar)}
					select {
					case mergedBars <- ev:
					case <-shutdown:
						return
					default:
						// Slow client: drop frame rather than blocking the publisher.
					}
				}
			}
		}(sym)
	}

	// Forward bars to the WebSocket client until the connection closes or a
	// write error occurs.
	for {
		select {
		case <-shutdown:
			return
		case ev, ok := <-mergedBars:
			if !ok {
				return
			}
			msg := wsBarMsg{Type: "bar", Symbol: ev.symbol, Bar: ev.bar}
			if err := wsConn.WriteJSON(msg); err != nil {
				slog.Debug("market ws: write error, closing",
					"service", "api", "symbol", ev.symbol, "err", err)
				return
			}
		}
	}
}

// ── fakeResponseWriter ────────────────────────────────────────────────────────

// fakeResponseWriter wraps a net.Conn so that it satisfies both
// http.ResponseWriter and http.Hijacker — the interfaces gorilla's Upgrader
// requires to perform the WebSocket handshake on an already-hijacked connection.
type fakeResponseWriter struct {
	conn   net.Conn
	header http.Header
	brw    *bufio.ReadWriter
}

func newFakeResponseWriter(conn net.Conn) *fakeResponseWriter {
	return &fakeResponseWriter{
		conn:   conn,
		header: make(http.Header),
		brw:    bufio.NewReadWriter(bufio.NewReader(conn), bufio.NewWriter(conn)),
	}
}

func (f *fakeResponseWriter) Header() http.Header { return f.header }

// WriteHeader is intentionally a no-op: gorilla writes the 101 response directly to netConn after Hijack().
func (f *fakeResponseWriter) WriteHeader(_ int) {}
func (f *fakeResponseWriter) Write(b []byte) (int, error)                 { return f.conn.Write(b) }
func (f *fakeResponseWriter) Hijack() (net.Conn, *bufio.ReadWriter, error) {
	return f.conn, f.brw, nil
}

// ── HTTP request builder ──────────────────────────────────────────────────────

// buildHTTPRequest creates a minimal *http.Request from a fasthttp context so
// gorilla's upgrader can validate the WebSocket handshake headers.
func buildHTTPRequest(fctx *fasthttp.RequestCtx) (*http.Request, error) {
	req, err := http.NewRequest(
		string(fctx.Method()),
		fctx.URI().String(),
		nil,
	)
	if err != nil {
		return nil, err
	}
	fctx.Request.Header.VisitAll(func(key, value []byte) {
		req.Header.Set(string(key), string(value))
	})
	return req, nil
}
