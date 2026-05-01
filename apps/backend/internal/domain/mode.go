package domain

// Mode is the bot operating mode.
type Mode string

const (
	ModeBacktest Mode = "backtest"
	ModePaper    Mode = "paper"
	ModeLive     Mode = "live"
)

func (m Mode) Valid() bool {
	switch m {
	case ModeBacktest, ModePaper, ModeLive:
		return true
	}
	return false
}
