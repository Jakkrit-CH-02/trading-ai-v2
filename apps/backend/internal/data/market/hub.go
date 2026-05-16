package market

import (
	"sync"

	"github.com/jakkrit-ch/trading-ai-v2/backend/internal/domain"
)

const subscriberBufSize = 8 // buffers ~8 one-minute bars before dropping

// Hub fans bar events out to zero or more per-symbol subscribers.
// Each subscriber gets its own buffered channel; slow readers drop frames
// rather than blocking the publisher.
type Hub struct {
	mu   sync.Mutex
	subs map[string][]chan domain.Bar
}

func NewHub() *Hub {
	return &Hub{subs: make(map[string][]chan domain.Bar)}
}

// Subscribe returns a channel that receives bars for the given symbol.
func (h *Hub) Subscribe(symbol string) <-chan domain.Bar {
	ch := make(chan domain.Bar, subscriberBufSize)
	h.mu.Lock()
	h.subs[symbol] = append(h.subs[symbol], ch)
	h.mu.Unlock()
	return ch
}

// Unsubscribe removes the channel from the subscriber list.
// The channel is not closed so callers that select on it will simply
// stop receiving new bars rather than seeing a spurious zero-value read.
func (h *Hub) Unsubscribe(symbol string, ch <-chan domain.Bar) {
	h.mu.Lock()
	defer h.mu.Unlock()
	list := h.subs[symbol]
	for i, c := range list {
		if c == ch {
			h.subs[symbol] = append(list[:i], list[i+1:]...)
			if len(h.subs[symbol]) == 0 {
				delete(h.subs, symbol)
			}
			return
		}
	}
}

// Publish sends bar to all subscribers of that symbol, dropping if full.
func (h *Hub) Publish(symbol string, bar domain.Bar) {
	h.mu.Lock()
	list := make([]chan domain.Bar, len(h.subs[symbol]))
	copy(list, h.subs[symbol])
	h.mu.Unlock()
	for _, ch := range list {
		select {
		case ch <- bar:
		default:
		}
	}
}
