package binance

import "github.com/shopspring/decimal"

// Config selects environment + credentials for the Binance client.
type Config struct {
	APIKey    string
	APISecret string
	Testnet   bool
	// RestBaseURL / WSBaseURL override the default endpoints when non-empty.
	// Mainly used by tests to point at httptest servers.
	RestBaseURL string
	WSBaseURL   string
	RecvWindow  int64 // ms, default 5000
}

const (
	mainnetREST = "https://api.binance.com"
	testnetREST = "https://testnet.binance.vision"
	mainnetWS   = "wss://stream.binance.com:9443"
	testnetWS   = "wss://stream.testnet.binance.vision"
)

// ExchangeInfo is a trimmed-down view of GET /api/v3/exchangeInfo.
type ExchangeInfo struct {
	Timezone   string         `json:"timezone"`
	ServerTime int64          `json:"serverTime"`
	Symbols    []SymbolInfo   `json:"symbols"`
	RateLimits []RateLimitDef `json:"rateLimits"`
}

type SymbolInfo struct {
	Symbol             string   `json:"symbol"`
	Status             string   `json:"status"`
	BaseAsset          string   `json:"baseAsset"`
	QuoteAsset         string   `json:"quoteAsset"`
	BaseAssetPrecision int      `json:"baseAssetPrecision"`
	QuotePrecision     int      `json:"quotePrecision"`
	OrderTypes         []string `json:"orderTypes"`
}

type RateLimitDef struct {
	RateLimitType string `json:"rateLimitType"`
	Interval      string `json:"interval"`
	IntervalNum   int    `json:"intervalNum"`
	Limit         int    `json:"limit"`
}

// AccountInfo is a trimmed-down view of GET /api/v3/account.
type AccountInfo struct {
	MakerCommission  int       `json:"makerCommission"`
	TakerCommission  int       `json:"takerCommission"`
	CanTrade         bool      `json:"canTrade"`
	CanWithdraw      bool      `json:"canWithdraw"`
	CanDeposit       bool      `json:"canDeposit"`
	UpdateTime       int64     `json:"updateTime"`
	AccountType      string    `json:"accountType"`
	Balances         []Balance `json:"balances"`
	Permissions      []string  `json:"permissions"`
}

type Balance struct {
	Asset  string          `json:"asset"`
	Free   decimal.Decimal `json:"free"`
	Locked decimal.Decimal `json:"locked"`
}

// OrderRequest is a normalized place-order payload.
type OrderRequest struct {
	Symbol      string
	Side        string // BUY / SELL
	Type        string // MARKET / LIMIT / STOP_LOSS_LIMIT etc.
	TimeInForce string // GTC / IOC / FOK (limit only)
	Quantity    decimal.Decimal
	Price       decimal.Decimal // limit only
	StopPrice   decimal.Decimal // stop variants only
	NewClientID string          // client order id (ULID from us)
}

// OrderResponse mirrors the Binance order ack/result.
type OrderResponse struct {
	Symbol              string          `json:"symbol"`
	OrderID             int64           `json:"orderId"`
	ClientOrderID       string          `json:"clientOrderId"`
	TransactTime        int64           `json:"transactTime"`
	Price               decimal.Decimal `json:"price"`
	OrigQty             decimal.Decimal `json:"origQty"`
	ExecutedQty         decimal.Decimal `json:"executedQty"`
	CummulativeQuoteQty decimal.Decimal `json:"cummulativeQuoteQty"`
	Status              string          `json:"status"`
	Type                string          `json:"type"`
	Side                string          `json:"side"`
}

// CancelRequest cancels by either exchange order id or client order id.
type CancelRequest struct {
	Symbol            string
	OrderID           int64
	OrigClientOrderID string
}

// KlinesQuery for GET /api/v3/klines.
type KlinesQuery struct {
	Symbol    string
	Interval  string
	StartMs   int64
	EndMs     int64
	Limit     int
}

// APIError is returned by Binance with an HTTP non-2xx and JSON `{code, msg}`.
type APIError struct {
	HTTPStatus int    `json:"-"`
	Code       int    `json:"code"`
	Msg        string `json:"msg"`
}

func (e *APIError) Error() string {
	return e.Msg
}
