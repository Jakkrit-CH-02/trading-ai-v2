package runtime

import (
	"errors"
	"testing"

	"github.com/stretchr/testify/require"
)

func TestFSM_LegalTransitions(t *testing.T) {
	tests := []struct {
		name string
		path []State
	}{
		{"idle->running->paused->running->idle", []State{StateRunning, StatePaused, StateRunning, StateIdle}},
		{"idle->running->idle", []State{StateRunning, StateIdle}},
		{"idle->halted->idle", []State{StateHalted, StateIdle}},
		{"running->halted", []State{StateRunning, StateHalted}},
		{"paused->halted", []State{StateRunning, StatePaused, StateHalted}},
	}
	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			f := NewFSM()
			for _, s := range tt.path {
				require.NoError(t, f.Transition(s))
				require.Equal(t, s, f.State())
			}
		})
	}
}

func TestFSM_IllegalTransitions(t *testing.T) {
	f := NewFSM()
	require.ErrorIs(t, f.Transition(StatePaused), ErrInvalidTransition) // idle->paused
	require.NoError(t, f.Transition(StateHalted))
	require.ErrorIs(t, f.Transition(StateRunning), ErrInvalidTransition) // halted->running
	require.ErrorIs(t, f.Transition(StatePaused), ErrInvalidTransition)  // halted->paused
	require.True(t, errors.Is(f.Transition(StatePaused), ErrInvalidTransition))
}
