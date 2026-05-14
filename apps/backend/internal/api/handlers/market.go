package handlers

import (
	"errors"
	"strconv"
	"strings"

	"github.com/gofiber/fiber/v2"

	"github.com/jakkrit-ch/trading-ai-v2/backend/internal/data"
	"github.com/jakkrit-ch/trading-ai-v2/backend/internal/data/market"
	"github.com/jakkrit-ch/trading-ai-v2/backend/internal/domain"
)

const (
	marketDefaultInterval = "1m"
	marketDefaultLimit    = 100
	marketMaxLimit        = 1000
)

type marketH struct {
	svc *market.Service
}

func newMarket(svc *market.Service) *marketH { return &marketH{svc: svc} }

func (h *marketH) symbols(c *fiber.Ctx) error {
	syms := h.svc.Symbols()
	out := make([]string, 0, len(syms))
	for _, s := range syms {
		out = append(out, string(s))
	}
	return writeOK(c, map[string]interface{}{"symbols": out})
}

// barDTO mirrors domain.Bar with decimals as strings.
type barDTO struct {
	Symbol    string `json:"symbol"`
	Interval  string `json:"interval"`
	OpenTime  int64  `json:"open_time"`
	CloseTime int64  `json:"close_time"`
	Open      string `json:"open"`
	High      string `json:"high"`
	Low       string `json:"low"`
	Close     string `json:"close"`
	Volume    string `json:"volume"`
}

func toBarDTO(b domain.Bar) barDTO {
	return barDTO{
		Symbol:    string(b.Symbol),
		Interval:  b.Interval,
		OpenTime:  b.OpenTime,
		CloseTime: b.CloseTime,
		Open:      b.Open.String(),
		High:      b.High.String(),
		Low:       b.Low.String(),
		Close:     b.Close.String(),
		Volume:    b.Volume.String(),
	}
}

func (h *marketH) candles(c *fiber.Ctx) error {
	sym, interval, ok := readMarketParams(c)
	if !ok {
		return nil
	}
	limit := marketDefaultLimit
	if v := strings.TrimSpace(c.Query("limit")); v != "" {
		n, err := strconv.Atoi(v)
		if err != nil || n <= 0 {
			return writeError(c, fiber.StatusBadRequest, "validation_failed", "limit must be a positive integer")
		}
		if n > marketMaxLimit {
			n = marketMaxLimit
		}
		limit = n
	}

	bars, err := h.svc.Candles(c.UserContext(), sym, interval, limit)
	if err != nil {
		return writeError(c, fiber.StatusInternalServerError, "internal", err.Error())
	}
	out := make([]barDTO, 0, len(bars))
	for _, b := range bars {
		out = append(out, toBarDTO(b))
	}
	return writeOK(c, map[string]interface{}{
		"symbol":   string(sym),
		"interval": interval,
		"bars":     out,
	})
}

func (h *marketH) snapshot(c *fiber.Ctx) error {
	sym, interval, ok := readMarketParams(c)
	if !ok {
		return nil
	}
	bar, source, err := h.svc.Snapshot(c.UserContext(), sym, interval)
	if err != nil {
		if errors.Is(err, data.ErrNotFound) {
			return writeError(c, fiber.StatusNotFound, "not_found", "no snapshot for symbol/interval")
		}
		return writeError(c, fiber.StatusInternalServerError, "internal", err.Error())
	}
	return writeOK(c, map[string]interface{}{
		"symbol":   string(sym),
		"interval": interval,
		"latest":   toBarDTO(bar),
		"source":   source,
	})
}

func readMarketParams(c *fiber.Ctx) (domain.Symbol, string, bool) {
	sym := strings.ToUpper(strings.TrimSpace(c.Query("symbol")))
	if sym == "" {
		_ = writeError(c, fiber.StatusBadRequest, "validation_failed", "symbol is required")
		return "", "", false
	}
	interval := strings.TrimSpace(c.Query("interval"))
	if interval == "" {
		interval = marketDefaultInterval
	}
	return domain.Symbol(sym), interval, true
}
