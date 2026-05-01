package decimalx

import (
	"fmt"

	"github.com/shopspring/decimal"
)

// Zero is a shared decimal zero.
var Zero = decimal.Zero

// FromString parses a decimal string, returning a wrapped error on failure.
func FromString(s string) (decimal.Decimal, error) {
	d, err := decimal.NewFromString(s)
	if err != nil {
		return decimal.Zero, fmt.Errorf("decimalx: parse %q: %w", s, err)
	}
	return d, nil
}

// MustFromString panics on parse failure. Use only for compile-time constants in tests.
func MustFromString(s string) decimal.Decimal {
	d, err := FromString(s)
	if err != nil {
		panic(err)
	}
	return d
}

// IsPositive reports whether d > 0.
func IsPositive(d decimal.Decimal) bool { return d.Sign() > 0 }

// IsNegative reports whether d < 0.
func IsNegative(d decimal.Decimal) bool { return d.Sign() < 0 }

// IsZero reports whether d == 0.
func IsZero(d decimal.Decimal) bool { return d.Sign() == 0 }
