package binance

import (
	"context"
	"sync"
	"time"
)

// TokenBucket is a simple in-memory token bucket suited for Binance's
// IP-based weight limit (1200/min by default).
type TokenBucket struct {
	mu         sync.Mutex
	capacity   float64
	tokens     float64
	refillRate float64 // tokens per second
	last       time.Time
	now        func() time.Time
}

// NewTokenBucket returns a bucket that refills `rate` tokens per second up
// to `capacity`. The bucket starts full.
func NewTokenBucket(capacity, ratePerSecond float64) *TokenBucket {
	return &TokenBucket{
		capacity:   capacity,
		tokens:     capacity,
		refillRate: ratePerSecond,
		now:        time.Now,
		last:       time.Now(),
	}
}

// Allow consumes `cost` tokens immediately if available; otherwise returns false.
func (b *TokenBucket) Allow(cost float64) bool {
	b.mu.Lock()
	defer b.mu.Unlock()
	b.refill()
	if b.tokens < cost {
		return false
	}
	b.tokens -= cost
	return true
}

// Wait blocks until `cost` tokens are available or ctx is done.
func (b *TokenBucket) Wait(ctx context.Context, cost float64) error {
	for {
		b.mu.Lock()
		b.refill()
		if b.tokens >= cost {
			b.tokens -= cost
			b.mu.Unlock()
			return nil
		}
		need := cost - b.tokens
		wait := time.Duration(need / b.refillRate * float64(time.Second))
		b.mu.Unlock()

		if wait <= 0 {
			wait = time.Millisecond
		}
		select {
		case <-ctx.Done():
			return ctx.Err()
		case <-time.After(wait):
		}
	}
}

func (b *TokenBucket) refill() {
	now := b.now()
	elapsed := now.Sub(b.last).Seconds()
	if elapsed <= 0 {
		return
	}
	b.tokens += elapsed * b.refillRate
	if b.tokens > b.capacity {
		b.tokens = b.capacity
	}
	b.last = now
}
