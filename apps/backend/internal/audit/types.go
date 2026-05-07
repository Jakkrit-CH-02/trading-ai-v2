// Package audit owns the append-only record of high-risk actions: live
// order submissions and kill-switch activations. Every live submit and every
// Kill must produce a row here — this is the system's tamper-evident trail.
package audit

import (
	"errors"
	"time"
)

// Action enumerates the audited operations.
type Action string

const (
	ActionLiveSubmit Action = "live_submit"
	ActionKill       Action = "kill"
	ActionReset      Action = "reset"
)

// Entry is one append-only audit row.
type Entry struct {
	ID        string
	Action    Action
	Actor     string // username or "system"
	Mode      string // execution mode at the time of action
	Entity    string // related entity ref: order id, symbol, etc.
	Details   string // free-form structured-text details
	CreatedAt time.Time
}

var ErrNotFound = errors.New("audit: not found")
