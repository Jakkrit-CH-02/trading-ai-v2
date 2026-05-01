package data

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"strings"
	"time"

	goredis "github.com/redis/go-redis/v9"

	"github.com/jakkrit-ch/trading-ai-v2/backend/internal/domain"
)

// RedisCache implements Cache against go-redis.
//
// Layout:
//
//	key:  market:bar:<SYMBOL>:<interval>     (string, JSON-encoded domain.Bar)
//	ttl:  configurable; 0 means no expiry.
type RedisCache struct {
	rdb *goredis.Client
	ttl time.Duration
}

// NewRedisCache wraps a redis client. ttl <= 0 disables expiration.
func NewRedisCache(rdb *goredis.Client, ttl time.Duration) *RedisCache {
	return &RedisCache{rdb: rdb, ttl: ttl}
}

func barKey(sym domain.Symbol, interval string) string {
	return "market:bar:" + strings.ToUpper(string(sym)) + ":" + interval
}

// SetLatestBar marshals the bar as JSON and writes it under barKey.
func (c *RedisCache) SetLatestBar(ctx context.Context, bar domain.Bar) error {
	if bar.Symbol == "" || bar.Interval == "" {
		return fmt.Errorf("redis cache: symbol and interval required")
	}
	payload, err := json.Marshal(bar)
	if err != nil {
		return fmt.Errorf("redis cache: marshal: %w", err)
	}
	if err := c.rdb.Set(ctx, barKey(bar.Symbol, bar.Interval), payload, c.ttl).Err(); err != nil {
		return fmt.Errorf("redis cache: set: %w", err)
	}
	return nil
}

// GetLatestBar reads the latest bar; returns ErrNotFound when the key is missing.
func (c *RedisCache) GetLatestBar(ctx context.Context, sym domain.Symbol, interval string) (domain.Bar, error) {
	raw, err := c.rdb.Get(ctx, barKey(sym, interval)).Bytes()
	if err != nil {
		if errors.Is(err, goredis.Nil) {
			return domain.Bar{}, ErrNotFound
		}
		return domain.Bar{}, fmt.Errorf("redis cache: get: %w", err)
	}
	var bar domain.Bar
	if err := json.Unmarshal(raw, &bar); err != nil {
		return domain.Bar{}, fmt.Errorf("redis cache: unmarshal: %w", err)
	}
	return bar, nil
}
