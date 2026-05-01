package ids

import (
	cryptorand "crypto/rand"
	"strings"
	"time"

	"github.com/oklog/ulid/v2"
)

// New returns a lowercase ULID string. Producer-side ID generation.
func New() string {
	t := ulid.Timestamp(time.Now().UTC())
	id := ulid.MustNew(t, cryptorand.Reader)
	return strings.ToLower(id.String())
}
