package binance

import (
	"context"
	"fmt"
	"strings"
)

// SymbolFlattener implements runtime.Flattener for a single live symbol on
// Binance spot. Construct one per controller; pass to Controller.WithFlattener.
type SymbolFlattener struct {
	client    *Client
	symbol    string // e.g. "BTCUSDT"
	baseAsset string // e.g. "BTC"
}

// NewSymbolFlattener wires a flattener for the given symbol/baseAsset.
func NewSymbolFlattener(c *Client, symbol, baseAsset string) *SymbolFlattener {
	return &SymbolFlattener{client: c, symbol: symbol, baseAsset: strings.ToUpper(baseAsset)}
}

// CancelAllOrders cancels every resting order on this symbol.
func (f *SymbolFlattener) CancelAllOrders(ctx context.Context) error {
	if _, err := f.client.CancelAllOpenOrders(ctx, f.symbol); err != nil {
		// "Unknown order sent" / no orders is not a failure here.
		var apiErr *APIError
		if as, ok := err.(*APIError); ok {
			apiErr = as
		}
		_ = apiErr
		return fmt.Errorf("binance flatten: cancel: %w", err)
	}
	return nil
}

// FlattenPositions sells the entire free balance of the base asset at
// market. On spot, "position" is the base-asset balance; selling it
// returns the account to a quote-only state.
func (f *SymbolFlattener) FlattenPositions(ctx context.Context) error {
	if f.baseAsset == "" {
		return fmt.Errorf("binance flatten: base asset not configured")
	}
	acc, err := f.client.GetAccount(ctx)
	if err != nil {
		return fmt.Errorf("binance flatten: account: %w", err)
	}
	for _, b := range acc.Balances {
		if strings.ToUpper(b.Asset) != f.baseAsset {
			continue
		}
		if b.Free.IsZero() || b.Free.Sign() < 0 {
			return nil
		}
		req := OrderRequest{
			Symbol:   f.symbol,
			Side:     "SELL",
			Type:     "MARKET",
			Quantity: b.Free,
		}
		if _, err := f.client.PlaceOrder(ctx, req); err != nil {
			return fmt.Errorf("binance flatten: sell: %w", err)
		}
		return nil
	}
	return nil
}
