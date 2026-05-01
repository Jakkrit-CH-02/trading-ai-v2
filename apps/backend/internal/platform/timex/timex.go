package timex

import "time"

// NowMs returns the current UTC time in Unix milliseconds.
func NowMs() int64 {
	return time.Now().UTC().UnixMilli()
}

// MsToTime converts UTC milliseconds back to time.Time in UTC.
func MsToTime(ms int64) time.Time {
	return time.UnixMilli(ms).UTC()
}
