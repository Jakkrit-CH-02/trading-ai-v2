// Package runtime owns the bot's execution loop. It wires the
// data → strategy → risk → order → tradelog pipeline together and gates it
// behind a small finite state machine (idle / running / paused / halted).
//
// Halted is the kill-switch terminal state from the risk policy. The full
// kill flow (cancel open orders + flatten + lock out) lands in Sprint 7;
// this package wires the FSM transition and the API surface so the rest of
// the system can already depend on it.
package runtime

import (
	"errors"
	"fmt"
	"sync"
)

// State is the bot's runtime state.
type State string

const (
	StateIdle    State = "idle"
	StateRunning State = "running"
	StatePaused  State = "paused"
	StateHalted  State = "halted"
)

// ErrInvalidTransition is returned by FSM.Transition when the requested
// (from, to) pair is not allowed.
var ErrInvalidTransition = errors.New("runtime: invalid state transition")

// allowed encodes the legal transitions. Halted is reachable from anywhere
// (kill switch); only an explicit reset returns it to idle.
var allowed = map[State]map[State]bool{
	StateIdle:    {StateRunning: true, StateHalted: true},
	StateRunning: {StatePaused: true, StateIdle: true, StateHalted: true},
	StatePaused:  {StateRunning: true, StateIdle: true, StateHalted: true},
	StateHalted:  {StateIdle: true},
}

// FSM is the goroutine-safe state machine guarding the controller.
type FSM struct {
	mu sync.RWMutex
	s  State
}

func NewFSM() *FSM { return &FSM{s: StateIdle} }

// State returns the current state.
func (f *FSM) State() State {
	f.mu.RLock()
	defer f.mu.RUnlock()
	return f.s
}

// Transition moves to `to` if (current, to) is in the allowed table.
func (f *FSM) Transition(to State) error {
	f.mu.Lock()
	defer f.mu.Unlock()
	if !allowed[f.s][to] {
		return fmt.Errorf("from=%s to=%s: %w", f.s, to, ErrInvalidTransition)
	}
	f.s = to
	return nil
}

// CompareAndSet is a small helper for callers that want to make a
// transition conditional on the current state.
func (f *FSM) CompareAndSet(from, to State) error {
	f.mu.Lock()
	defer f.mu.Unlock()
	if f.s != from {
		return fmt.Errorf("expected=%s actual=%s: %w", from, f.s, ErrInvalidTransition)
	}
	if !allowed[f.s][to] {
		return fmt.Errorf("from=%s to=%s: %w", f.s, to, ErrInvalidTransition)
	}
	f.s = to
	return nil
}
