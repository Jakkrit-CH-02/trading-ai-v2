package domain

import "github.com/shopspring/decimal"

type Side string

const (
	SideBuy  Side = "buy"
	SideSell Side = "sell"
)

type OrderType string

const (
	OrderTypeMarket OrderType = "market"
	OrderTypeLimit  OrderType = "limit"
)

type OrderStatus string

const (
	OrderStatusNew      OrderStatus = "new"
	OrderStatusFilled   OrderStatus = "filled"
	OrderStatusCanceled OrderStatus = "canceled"
	OrderStatusRejected OrderStatus = "rejected"
)

// Order represents a trading order in our system.
type Order struct {
	ID         string          `json:"id"`
	Symbol     Symbol          `json:"symbol"`
	Side       Side            `json:"side"`
	Type       OrderType       `json:"type"`
	Qty        decimal.Decimal `json:"qty"`
	Price      decimal.Decimal `json:"price"`
	StopPrice  decimal.Decimal `json:"stop_price"`
	Status     OrderStatus     `json:"status"`
	Mode       Mode            `json:"mode"`
	CreatedMs  int64           `json:"created_ms"`
	UpdatedMs  int64           `json:"updated_ms"`
	ExchangeID string          `json:"exchange_id,omitempty"`
}
