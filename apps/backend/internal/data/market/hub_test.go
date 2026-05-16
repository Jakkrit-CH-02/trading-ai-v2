package market_test

import (
	"testing"
	"time"

	"github.com/jakkrit-ch/trading-ai-v2/backend/internal/data/market"
	"github.com/jakkrit-ch/trading-ai-v2/backend/internal/domain"
	"github.com/shopspring/decimal"
	"github.com/stretchr/testify/require"
)

func TestHub_PublishDeliversToSubscriber(t *testing.T) {
	h := market.NewHub()

	ch := h.Subscribe("BTCUSDT")
	defer h.Unsubscribe("BTCUSDT", ch)

	bar := domain.Bar{Symbol: "BTCUSDT", Close: decimal.NewFromFloat(50000)}
	h.Publish("BTCUSDT", bar)

	select {
	case got := <-ch:
		require.Equal(t, bar, got)
	case <-time.After(100 * time.Millisecond):
		t.Fatal("timeout: no bar received")
	}
}

func TestHub_UnsubscribeStopsDelivery(t *testing.T) {
	h := market.NewHub()

	ch := h.Subscribe("BTCUSDT")
	h.Unsubscribe("BTCUSDT", ch)

	bar := domain.Bar{Symbol: "BTCUSDT", Close: decimal.NewFromFloat(50000)}
	h.Publish("BTCUSDT", bar)

	select {
	case <-ch:
		t.Fatal("received bar after unsubscribe")
	case <-time.After(50 * time.Millisecond):
		// expected
	}
}

func TestHub_MultipleSubscribersReceiveSameBar(t *testing.T) {
	h := market.NewHub()

	ch1 := h.Subscribe("BTCUSDT")
	ch2 := h.Subscribe("BTCUSDT")
	defer h.Unsubscribe("BTCUSDT", ch1)
	defer h.Unsubscribe("BTCUSDT", ch2)

	bar := domain.Bar{Symbol: "BTCUSDT", Close: decimal.NewFromFloat(51000)}
	h.Publish("BTCUSDT", bar)

	for _, ch := range []<-chan domain.Bar{ch1, ch2} {
		select {
		case got := <-ch:
			require.Equal(t, bar, got)
		case <-time.After(100 * time.Millisecond):
			t.Fatal("timeout: subscriber did not receive bar")
		}
	}
}
