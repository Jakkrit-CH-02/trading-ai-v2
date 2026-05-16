package handlers

import (
	"bufio"
	"log/slog"
	"net"
	"net/http"
	"sync"

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
	var sub wsSubscribeMsg
	if err := wsConn.ReadJSON(&sub); err != nil {
		slog.Warn("market ws: read subscribe failed", "service", "api", "err", err)
		return
	}
	if sub.Type != "subscribe" || len(sub.Symbols) == 0 {
		_ = wsConn.WriteJSON(map[string]string{
			"type":    "error",
			"message": "expected subscribe message with at least one symbol",
		})
		return
	}

	// done is closed to signal all fan-in goroutines to exit.
	done := make(chan struct{})
	var closeOnce sync.Once
	closeDone := func() { closeOnce.Do(func() { close(done) }) }
	defer closeDone()

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
				case <-done:
					return
				case bar, ok := <-ch:
					if !ok {
						return
					}
					ev := barEvent{symbol: symbol, bar: toBarDTO(bar)}
					select {
					case mergedBars <- ev:
					case <-done:
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
		case <-done:
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

func (f *fakeResponseWriter) Header() http.Header                          { return f.header }
func (f *fakeResponseWriter) WriteHeader(_ int)                            {}
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
