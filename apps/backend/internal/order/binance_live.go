package order

import (
	"context"
	"fmt"
	"strings"

	"github.com/jakkrit-ch/trading-ai-v2/backend/internal/binance"
	"github.com/jakkrit-ch/trading-ai-v2/backend/internal/domain"
	"github.com/jakkrit-ch/trading-ai-v2/backend/internal/platform/timex"
)

// BinanceLiveExecutor adapts internal/binance.Client to the Executor
// interface. It is wrapped by LiveExecutor — never installed directly into
// the Router. The four-condition livegate runs upstream of every call.
type BinanceLiveExecutor struct {
	client *binance.Client
}

func NewBinanceLiveExecutor(client *binance.Client) *BinanceLiveExecutor {
	return &BinanceLiveExecutor{client: client}
}

func (b *BinanceLiveExecutor) Place(ctx context.Context, o domain.Order) (domain.Order, error) {
	req := binance.OrderRequest{
		Symbol:      string(o.Symbol),
		Side:        strings.ToUpper(string(o.Side)),
		Type:        strings.ToUpper(string(o.Type)),
		Quantity:    o.Qty,
		Price:       o.Price,
		StopPrice:   o.StopPrice,
		NewClientID: o.ID,
	}
	if o.Type == domain.OrderTypeLimit {
		req.TimeInForce = "GTC"
	}
	resp, err := b.client.PlaceOrder(ctx, req)
	if err != nil {
		return domain.Order{}, fmt.Errorf("binance place: %w", err)
	}
	now := timex.NowMs()
	placed := o
	placed.Status = mapBinanceStatus(resp.Status)
	placed.ExchangeID = fmt.Sprintf("%d", resp.OrderID)
	if !resp.Price.IsZero() {
		placed.Price = resp.Price
	}
	placed.UpdatedMs = now
	return placed, nil
}

func mapBinanceStatus(s string) domain.OrderStatus {
	switch strings.ToUpper(s) {
	case "FILLED":
		return domain.OrderStatusFilled
	case "CANCELED", "EXPIRED":
		return domain.OrderStatusCanceled
	case "REJECTED":
		return domain.OrderStatusRejected
	default:
		return domain.OrderStatusNew
	}
}
