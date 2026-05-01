package domain

import "github.com/shopspring/decimal"

// Bar is a single OHLCV candle. Times are UTC milliseconds.
type Bar struct {
	Symbol    Symbol          `json:"symbol"`
	Interval  string          `json:"interval"`
	OpenTime  int64           `json:"open_time"`
	CloseTime int64           `json:"close_time"`
	Open      decimal.Decimal `json:"open"`
	High      decimal.Decimal `json:"high"`
	Low       decimal.Decimal `json:"low"`
	Close     decimal.Decimal `json:"close"`
	Volume    decimal.Decimal `json:"volume"`
}
