package binance

import (
	"context"
	"fmt"
	"sync/atomic"
)

// PermissionResult is the outcome of the startup-time API key permission
// check. The live gate consults this to decide whether condition (c) holds.
type PermissionResult struct {
	CanTrade    bool
	CanWithdraw bool
}

// OK reports whether the key is safe for live trading: must be able to
// trade and must NOT be able to withdraw.
func (p PermissionResult) OK() bool { return p.CanTrade && !p.CanWithdraw }

// PermissionState is a goroutine-safe holder for the PermissionResult.
// Configure once at startup; the live gate reads OK() per request.
type PermissionState struct {
	v atomic.Pointer[PermissionResult]
}

func NewPermissionState() *PermissionState { return &PermissionState{} }

// Set stores the most recent permission probe result.
func (s *PermissionState) Set(r PermissionResult) { s.v.Store(&r) }

// OK reports whether the latest probe passed.
func (s *PermissionState) OK() bool {
	r := s.v.Load()
	if r == nil {
		return false
	}
	return r.OK()
}

// CheckPermissions calls GET /api/v3/account and returns whether the
// configured key can trade but cannot withdraw. The caller wires the result
// into the live gate at startup.
func (c *Client) CheckPermissions(ctx context.Context) (PermissionResult, error) {
	acc, err := c.GetAccount(ctx)
	if err != nil {
		return PermissionResult{}, fmt.Errorf("binance: permission probe: %w", err)
	}
	return PermissionResult{
		CanTrade:    acc.CanTrade,
		CanWithdraw: acc.CanWithdraw,
	}, nil
}
