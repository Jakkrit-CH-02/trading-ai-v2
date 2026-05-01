package domain

// Symbol is an exchange trading pair, e.g. "BTCUSDT".
type Symbol string

func (s Symbol) String() string { return string(s) }
