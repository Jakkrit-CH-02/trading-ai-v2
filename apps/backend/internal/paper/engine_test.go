package paper

import (
	"context"
	"testing"

	"github.com/shopspring/decimal"
	"github.com/stretchr/testify/require"

	"github.com/jakkrit-ch/trading-ai-v2/backend/internal/domain"
)

const sym = domain.Symbol("BTCUSDT")

func dec(s string) decimal.Decimal {
	d, _ := decimal.NewFromString(s)
	return d
}

func bar(close string) domain.Bar {
	c := dec(close)
	return domain.Bar{Symbol: sym, Close: c, High: c, Low: c, Open: c, CloseTime: 1}
}

// buyOrder returns a filled BUY order at the given price with SL/TP/trail set.
func buyOrder(qty, stopPrice, takeProfit, trailActivation, trailPct string) domain.Order {
	return domain.Order{
		Symbol:             sym,
		Side:               domain.SideBuy,
		Type:               domain.OrderTypeMarket,
		Qty:                dec(qty),
		StopPrice:          dec(stopPrice),
		TakeProfit:         dec(takeProfit),
		TrailActivationPct: dec(trailActivation),
		TrailPct:           dec(trailPct),
		Mode:               domain.ModePaper,
	}
}

// seedBuy places a buy after calling OnBar at price, drains the fill event.
func seedBuy(t *testing.T, eng *Engine, price string, o domain.Order) {
	t.Helper()
	eng.OnBar(bar(price))
	_, err := eng.Place(context.Background(), o)
	require.NoError(t, err)
	<-eng.Events() // drain buy fill event
}

// ---- Place / basic accounting -----------------------------------------------

func TestPlace_Buy_DeductsCash(t *testing.T) {
	eng := NewEngine(dec("100000"))
	eng.OnBar(bar("50000"))
	o := buyOrder("1", "49000", "0", "0", "0")
	filled, err := eng.Place(context.Background(), o)
	require.NoError(t, err)
	require.Equal(t, domain.OrderStatusFilled, filled.Status)

	// fill = 50000 * (1 + 0.0001) = 50005
	expectedFill := dec("50005")
	require.True(t, filled.Price.Equal(expectedFill), "fill=%s", filled.Price)
	require.True(t, eng.Cash().LessThan(dec("100000")), "cash should decrease after buy")
}

func TestPlace_Buy_SetsExitFields(t *testing.T) {
	eng := NewEngine(dec("100000"))
	seedBuy(t, eng, "100", buyOrder("1", "95", "110", "0.01", "0.015"))

	positions := eng.Positions()
	require.Len(t, positions, 1)
	p := positions[0]
	require.True(t, p.StopLoss.Equal(dec("95")))
	require.True(t, p.TakeProfit.Equal(dec("110")))
	require.True(t, p.TrailActivationPct.Equal(dec("0.01")))
	require.True(t, p.TrailPct.Equal(dec("0.015")))
	require.True(t, p.TrailHigh.IsPositive(), "TrailHigh should be seeded at fill price")
}

func TestPlace_Sell_RealizesPL(t *testing.T) {
	eng := NewEngine(dec("100000"))
	seedBuy(t, eng, "100", buyOrder("1", "90", "0", "0", "0"))

	// Sell at 110.
	eng.OnBar(bar("110"))
	sell := domain.Order{
		Symbol: sym,
		Side:   domain.SideSell,
		Type:   domain.OrderTypeMarket,
		Qty:    dec("1"),
		Mode:   domain.ModePaper,
	}
	_, err := eng.Place(context.Background(), sell)
	require.NoError(t, err)
	require.Empty(t, eng.Positions(), "position should be flat after sell")
	// Cash should be more than initial (profit trade).
	require.True(t, eng.Cash().GreaterThan(dec("100000")))
}

func TestPlace_InsufficientCash(t *testing.T) {
	eng := NewEngine(dec("100"))
	eng.OnBar(bar("50000"))
	o := buyOrder("10", "40000", "0", "0", "0")
	_, err := eng.Place(context.Background(), o)
	require.ErrorIs(t, err, ErrInsufficientCash)
}

func TestPlace_InsufficientPosition(t *testing.T) {
	eng := NewEngine(dec("100000"))
	seedBuy(t, eng, "100", buyOrder("1", "90", "0", "0", "0"))
	eng.OnBar(bar("110"))
	sell := domain.Order{Symbol: sym, Side: domain.SideSell, Type: domain.OrderTypeMarket, Qty: dec("5"), Mode: domain.ModePaper}
	_, err := eng.Place(context.Background(), sell)
	require.ErrorIs(t, err, ErrInsufficientPosition)
}

func TestPlace_NoMarketPrice(t *testing.T) {
	eng := NewEngine(dec("100000"))
	o := buyOrder("1", "90", "0", "0", "0")
	_, err := eng.Place(context.Background(), o)
	require.ErrorIs(t, err, ErrNoMarketPrice)
}

// ---- CheckExits: stop loss --------------------------------------------------

func TestCheckExits_StopLoss_Triggers(t *testing.T) {
	eng := NewEngine(dec("100000"))
	// Buy at 100, SL at 95.
	seedBuy(t, eng, "100", buyOrder("1", "95", "0", "0", "0"))

	// Price drops to 90 (below SL of 95).
	orders, err := eng.CheckExits(context.Background(), bar("90"))
	require.NoError(t, err)
	require.Len(t, orders, 1)
	require.Equal(t, domain.SideSell, orders[0].Side)
	require.Equal(t, domain.OrderStatusFilled, orders[0].Status)
	require.Empty(t, eng.Positions(), "position should be flat after SL exit")

	evt := <-eng.Events()
	require.Equal(t, "stop_loss", evt.ExitReason)
}

func TestCheckExits_StopLoss_NoTrigger_Above(t *testing.T) {
	eng := NewEngine(dec("100000"))
	seedBuy(t, eng, "100", buyOrder("1", "95", "0", "0", "0"))

	orders, err := eng.CheckExits(context.Background(), bar("96"))
	require.NoError(t, err)
	require.Empty(t, orders, "SL should not trigger when price is above SL")
	require.Len(t, eng.Positions(), 1)
}

func TestCheckExits_StopLoss_ExactLevel(t *testing.T) {
	eng := NewEngine(dec("100000"))
	seedBuy(t, eng, "100", buyOrder("1", "95", "0", "0", "0"))

	// Price at exactly SL level should trigger (LessThanOrEqual).
	orders, err := eng.CheckExits(context.Background(), bar("95"))
	require.NoError(t, err)
	require.Len(t, orders, 1)
}

// ---- CheckExits: take profit ------------------------------------------------

func TestCheckExits_TakeProfit_Triggers(t *testing.T) {
	eng := NewEngine(dec("100000"))
	// Buy at 100, TP at 115.
	seedBuy(t, eng, "100", buyOrder("1", "90", "115", "0", "0"))

	orders, err := eng.CheckExits(context.Background(), bar("120"))
	require.NoError(t, err)
	require.Len(t, orders, 1)
	require.Equal(t, domain.SideSell, orders[0].Side)
	require.Empty(t, eng.Positions())

	evt := <-eng.Events()
	require.Equal(t, "take_profit", evt.ExitReason)
}

func TestCheckExits_TakeProfit_NoTrigger_Below(t *testing.T) {
	eng := NewEngine(dec("100000"))
	seedBuy(t, eng, "100", buyOrder("1", "90", "115", "0", "0"))

	orders, err := eng.CheckExits(context.Background(), bar("114"))
	require.NoError(t, err)
	require.Empty(t, orders)
}

func TestCheckExits_TakeProfit_ExactLevel(t *testing.T) {
	eng := NewEngine(dec("100000"))
	seedBuy(t, eng, "100", buyOrder("1", "90", "115", "0", "0"))

	orders, err := eng.CheckExits(context.Background(), bar("115"))
	require.NoError(t, err)
	require.Len(t, orders, 1)
}

func TestCheckExits_ZeroTP_DoesNotTrigger(t *testing.T) {
	eng := NewEngine(dec("100000"))
	// TP = 0 means disabled.
	seedBuy(t, eng, "100", buyOrder("1", "90", "0", "0", "0"))

	orders, err := eng.CheckExits(context.Background(), bar("999"))
	require.NoError(t, err)
	require.Empty(t, orders)
}

// ---- CheckExits: no position ------------------------------------------------

func TestCheckExits_NoPosition_ReturnsNil(t *testing.T) {
	eng := NewEngine(dec("100000"))
	eng.OnBar(bar("100"))
	orders, err := eng.CheckExits(context.Background(), bar("50"))
	require.NoError(t, err)
	require.Nil(t, orders)
}

// ---- OnBar: trailing stop advancement ---------------------------------------

func TestOnBar_TrailingStop_AdvancesAfterActivation(t *testing.T) {
	eng := NewEngine(dec("100000"))
	// Buy at 100, trail activates at +1% (101), trail distance 2%.
	seedBuy(t, eng, "100", buyOrder("1", "90", "0", "0.01", "0.02"))

	initialSL := eng.Positions()[0].StopLoss // = 90 (hard SL set at buy)

	// Price rises to 102 — above activation (101). Trail should kick in.
	// newSL = 102 * (1 - 0.02) = 99.96, which is > 90, so SL should rise.
	eng.OnBar(bar("102"))
	positions := eng.Positions()
	require.Len(t, positions, 1)
	require.True(t, positions[0].StopLoss.GreaterThan(initialSL),
		"trailing SL should rise above initial hard SL after activation: got %s", positions[0].StopLoss)

	// Price rises higher to 110. SL should rise further.
	eng.OnBar(bar("110"))
	sl110 := eng.Positions()[0].StopLoss
	// newSL = 110 * (1 - 0.02) = 107.8
	expected110 := dec("107.8")
	require.True(t, sl110.GreaterThanOrEqual(expected110),
		"SL should trail to ~%s, got %s", expected110, sl110)

	// Price pulls back to 108 (still above SL). SL should NOT decrease.
	eng.OnBar(bar("108"))
	slAfterPullback := eng.Positions()[0].StopLoss
	require.True(t, slAfterPullback.Equal(sl110),
		"SL must not decrease on pullback: was %s, now %s", sl110, slAfterPullback)
}

func TestOnBar_TrailingStop_DoesNotActivateBeforeThreshold(t *testing.T) {
	eng := NewEngine(dec("100000"))
	// Trail activates at +5%.
	seedBuy(t, eng, "100", buyOrder("1", "90", "0", "0.05", "0.02"))
	initialSL := eng.Positions()[0].StopLoss

	// Price rises to 104 — below the 5% activation level (105).
	eng.OnBar(bar("104"))
	require.True(t, eng.Positions()[0].StopLoss.Equal(initialSL),
		"SL must not change before activation threshold")
}

func TestOnBar_NoTrail_SLUnchanged(t *testing.T) {
	eng := NewEngine(dec("100000"))
	// No trailing (TrailPct = 0).
	seedBuy(t, eng, "100", buyOrder("1", "90", "0", "0", "0"))
	initialSL := eng.Positions()[0].StopLoss

	eng.OnBar(bar("200")) // big price move
	require.True(t, eng.Positions()[0].StopLoss.Equal(initialSL),
		"SL should not change without trailing enabled")
}

// ---- TrailingStop + CheckExits integration ----------------------------------

func TestTrailingStop_RaisedSL_TriggersOnPullback(t *testing.T) {
	ctx := context.Background()
	eng := NewEngine(dec("100000"))
	// Buy at 100, trail activates at +1%, trail 2%.
	seedBuy(t, eng, "100", buyOrder("1", "90", "0", "0.01", "0.02"))

	// Push price up to 110; SL should trail to ~107.8.
	eng.OnBar(bar("110"))
	raisedSL := eng.Positions()[0].StopLoss
	require.True(t, raisedSL.GreaterThan(dec("90")), "SL should have risen: %s", raisedSL)

	// Price drops below the raised SL → CheckExits should fire stop_loss.
	trigger := raisedSL.Sub(dec("1"))
	orders, err := eng.CheckExits(ctx, bar(trigger.String()))
	require.NoError(t, err)
	require.Len(t, orders, 1, "trailing SL should trigger on pullback below raised level")
	evt := <-eng.Events()
	require.Equal(t, "stop_loss", evt.ExitReason)
}

// ---- Equity / accounting ----------------------------------------------------

func TestEquity_IncludesOpenPosition(t *testing.T) {
	eng := NewEngine(dec("100000"))
	eng.OnBar(bar("100"))
	o := buyOrder("10", "90", "0", "0", "0")
	_, err := eng.Place(context.Background(), o)
	require.NoError(t, err)

	// Mark up the position price.
	eng.OnBar(bar("120"))
	equity := eng.Equity()
	// Equity > initial because position gained value.
	require.True(t, equity.GreaterThan(dec("100000")),
		"equity should reflect mark-to-market gain: %s", equity)
}

// ---- Reset ------------------------------------------------------------------

func TestReset_ClearsPositionsAndRestoresCash(t *testing.T) {
	eng := NewEngine(dec("100000"))
	seedBuy(t, eng, "100", buyOrder("1", "90", "0", "0", "0"))
	require.Len(t, eng.Positions(), 1)

	eng.Reset()
	require.Empty(t, eng.Positions())
	require.True(t, eng.Cash().Equal(dec("100000")))
}

// ---- DailyPnL ---------------------------------------------------------------

func TestEngine_DailyPnL_StartsAtZero(t *testing.T) {
	eng := NewEngine(decimal.NewFromInt(10_000))
	require.True(t, eng.DailyPnL().IsZero(), "no trades → daily PnL must be zero")
}

func TestEngine_DailyPnL_AccumulatesWithinDay(t *testing.T) {
	ctx := context.Background()
	eng := NewEngine(decimal.NewFromInt(10_000))

	eng.OnBar(domain.Bar{Symbol: "BTCUSDT", Close: decimal.NewFromInt(100)})

	bo := domain.Order{
		ID: "o1", Symbol: "BTCUSDT", Side: domain.SideBuy,
		Type: domain.OrderTypeMarket, Qty: decimal.NewFromInt(10),
		StopPrice: decimal.NewFromInt(90),
		Mode:      domain.ModePaper,
	}
	_, err := eng.Place(ctx, bo)
	require.NoError(t, err)

	eng.OnBar(domain.Bar{Symbol: "BTCUSDT", Close: decimal.NewFromInt(110)})
	so := domain.Order{
		ID: "o2", Symbol: "BTCUSDT", Side: domain.SideSell,
		Type: domain.OrderTypeMarket, Qty: decimal.NewFromInt(10),
		Mode: domain.ModePaper,
	}
	_, err = eng.Place(ctx, so)
	require.NoError(t, err)

	require.True(t, eng.DailyPnL().IsPositive(), "profitable day → daily PnL must be positive")
}

func TestEngine_DailyPnL_ResetAfterReset(t *testing.T) {
	ctx := context.Background()
	eng := NewEngine(decimal.NewFromInt(10_000))
	eng.OnBar(domain.Bar{Symbol: "BTCUSDT", Close: decimal.NewFromInt(100)})
	buy := domain.Order{
		ID: "o3", Symbol: "BTCUSDT", Side: domain.SideBuy,
		Type: domain.OrderTypeMarket, Qty: decimal.NewFromInt(5),
		StopPrice: decimal.NewFromInt(90), Mode: domain.ModePaper,
	}
	_, err := eng.Place(ctx, buy)
	require.NoError(t, err)
	eng.OnBar(domain.Bar{Symbol: "BTCUSDT", Close: decimal.NewFromInt(110)})
	sell := domain.Order{
		ID: "o4", Symbol: "BTCUSDT", Side: domain.SideSell,
		Type: domain.OrderTypeMarket, Qty: decimal.NewFromInt(5),
		Mode: domain.ModePaper,
	}
	_, err = eng.Place(ctx, sell)
	require.NoError(t, err)

	eng.Reset()
	require.True(t, eng.DailyPnL().IsZero(), "after Reset daily PnL must be zero")
}

func TestEngine_DailyPnL_AccumulatesFromCheckExits(t *testing.T) {
	ctx := context.Background()
	eng := NewEngine(decimal.NewFromInt(10_000))

	// Seed price and open a position.
	eng.OnBar(domain.Bar{Symbol: "BTCUSDT", Close: decimal.NewFromInt(100)})
	bo := domain.Order{
		ID: "ceo1", Symbol: "BTCUSDT", Side: domain.SideBuy,
		Type: domain.OrderTypeMarket, Qty: decimal.NewFromInt(5),
		StopPrice: decimal.NewFromInt(90), Mode: domain.ModePaper,
	}
	_, err := eng.Place(ctx, bo)
	require.NoError(t, err)

	// Trigger a stop-loss exit via CheckExits: price drops below stop.
	lowBar := domain.Bar{
		Symbol: "BTCUSDT",
		Close:  decimal.NewFromInt(85), // below stop of 90
		Low:    decimal.NewFromInt(85),
		High:   decimal.NewFromInt(85),
	}
	eng.OnBar(lowBar)
	exits, err := eng.CheckExits(ctx, lowBar)
	require.NoError(t, err)
	require.NotEmpty(t, exits, "stop-loss must fire")

	// The auto-exit at a loss should make DailyPnL negative.
	require.True(t, eng.DailyPnL().IsNegative(),
		"stop-loss exit below entry → daily PnL must be negative, got %s", eng.DailyPnL())
}

func TestEngine_DailyPnL_NegativeOnLosingDay(t *testing.T) {
	ctx := context.Background()
	eng := NewEngine(decimal.NewFromInt(10_000))

	eng.OnBar(domain.Bar{Symbol: "BTCUSDT", Close: decimal.NewFromInt(100)})
	bo := domain.Order{
		ID: "neg1", Symbol: "BTCUSDT", Side: domain.SideBuy,
		Type: domain.OrderTypeMarket, Qty: decimal.NewFromInt(10),
		StopPrice: decimal.NewFromInt(50), Mode: domain.ModePaper,
	}
	_, err := eng.Place(ctx, bo)
	require.NoError(t, err)

	// Sell at 90 — a loss vs entry of ~100.
	eng.OnBar(domain.Bar{Symbol: "BTCUSDT", Close: decimal.NewFromInt(90)})
	so := domain.Order{
		ID: "neg2", Symbol: "BTCUSDT", Side: domain.SideSell,
		Type: domain.OrderTypeMarket, Qty: decimal.NewFromInt(10),
		Mode: domain.ModePaper,
	}
	_, err = eng.Place(ctx, so)
	require.NoError(t, err)

	require.True(t, eng.DailyPnL().IsNegative(),
		"selling below entry → daily PnL must be negative, got %s", eng.DailyPnL())
}

// ---- Short selling: Place ---------------------------------------------------

func sellOrder(qty, stopPrice, takeProfit, trailActivation, trailPct string) domain.Order {
	return domain.Order{
		Symbol:             sym,
		Side:               domain.SideSell,
		Type:               domain.OrderTypeMarket,
		Qty:                dec(qty),
		StopPrice:          dec(stopPrice),
		TakeProfit:         dec(takeProfit),
		TrailActivationPct: dec(trailActivation),
		TrailPct:           dec(trailPct),
		Mode:               domain.ModePaper,
	}
}

// seedShort opens a short after calling OnBar at price, drains the fill event.
func seedShort(t *testing.T, eng *Engine, price string, o domain.Order) {
	t.Helper()
	eng.OnBar(bar(price))
	_, err := eng.Place(context.Background(), o)
	require.NoError(t, err)
	<-eng.Events() // drain fill event
}

func TestPlace_Short_CreditsCash(t *testing.T) {
	eng := NewEngine(dec("100000"))
	eng.OnBar(bar("50000"))
	o := sellOrder("1", "52000", "0", "0", "0") // SL above entry for shorts
	initialCash := eng.Cash()
	_, err := eng.Place(context.Background(), o)
	require.NoError(t, err)
	// fill = 50000 * (1 - 0.0001) = 49995; cash increases
	require.True(t, eng.Cash().GreaterThan(initialCash), "opening short must credit cash")
}

func TestPlace_Short_SetsPositionFields(t *testing.T) {
	eng := NewEngine(dec("100000"))
	seedShort(t, eng, "100", sellOrder("2", "105", "85", "0.01", "0.015"))

	positions := eng.Positions()
	require.Len(t, positions, 1)
	p := positions[0]
	require.Equal(t, domain.SideSell, p.Side)
	require.True(t, p.Qty.Equal(dec("2")))
	require.True(t, p.StopLoss.Equal(dec("105")))
	require.True(t, p.TakeProfit.Equal(dec("85")))
	require.True(t, p.TrailLow.IsPositive(), "TrailLow should be seeded at fill price")
}

func TestPlace_Cover_RealizesProfitWhenPriceFell(t *testing.T) {
	eng := NewEngine(dec("100000"))
	// Short at 100; price falls to 80; cover.
	seedShort(t, eng, "100", sellOrder("1", "105", "0", "0", "0"))
	cashAfterOpen := eng.Cash()

	eng.OnBar(bar("80"))
	buy := domain.Order{Symbol: sym, Side: domain.SideBuy, Type: domain.OrderTypeMarket, Qty: dec("1"), Mode: domain.ModePaper}
	_, err := eng.Place(context.Background(), buy)
	require.NoError(t, err)
	<-eng.Events()

	require.Empty(t, eng.Positions(), "position should be flat after cover")
	// covering at 80 < entry ~99.99 → profit → cash > cashAfterOpen
	require.True(t, eng.Cash().GreaterThan(cashAfterOpen), "covering at lower price should profit")
}

func TestPlace_Cover_RealizesLossWhenPriceRose(t *testing.T) {
	eng := NewEngine(dec("100000"))
	// Short at 100; price rises to 120; cover at a loss.
	seedShort(t, eng, "100", sellOrder("1", "110", "0", "0", "0"))
	cashAfterOpen := eng.Cash()

	eng.OnBar(bar("120"))
	buy := domain.Order{Symbol: sym, Side: domain.SideBuy, Type: domain.OrderTypeMarket, Qty: dec("1"), Mode: domain.ModePaper}
	_, err := eng.Place(context.Background(), buy)
	require.NoError(t, err)
	<-eng.Events()

	require.Empty(t, eng.Positions())
	require.True(t, eng.Cash().LessThan(cashAfterOpen), "covering at higher price should lose")
}

func TestPlace_Cover_PartialLeavesShortOpen(t *testing.T) {
	eng := NewEngine(dec("100000"))
	seedShort(t, eng, "100", sellOrder("3", "110", "0", "0", "0"))

	eng.OnBar(bar("90"))
	buy := domain.Order{Symbol: sym, Side: domain.SideBuy, Type: domain.OrderTypeMarket, Qty: dec("1"), Mode: domain.ModePaper}
	_, err := eng.Place(context.Background(), buy)
	require.NoError(t, err)
	<-eng.Events()

	positions := eng.Positions()
	require.Len(t, positions, 1)
	require.True(t, positions[0].Qty.Equal(dec("2")), "2 of 3 still short")
	require.Equal(t, domain.SideSell, positions[0].Side)
}

func TestPlace_Cover_ExceedsQtyReturnsError(t *testing.T) {
	eng := NewEngine(dec("100000"))
	seedShort(t, eng, "100", sellOrder("1", "110", "0", "0", "0"))

	eng.OnBar(bar("90"))
	buy := domain.Order{Symbol: sym, Side: domain.SideBuy, Type: domain.OrderTypeMarket, Qty: dec("5"), Mode: domain.ModePaper}
	_, err := eng.Place(context.Background(), buy)
	require.ErrorIs(t, err, ErrInsufficientPosition)
}
