package redis

import (
	"context"
	"fmt"
	"time"

	goredis "github.com/redis/go-redis/v9"

	"github.com/jakkrit-ch/trading-ai-v2/backend/internal/platform/config"
)

// New creates a redis client from RedisConfig and verifies connectivity with a ping.
func New(ctx context.Context, cfg config.RedisConfig) (*goredis.Client, error) {
	if cfg.Addr == "" {
		return nil, fmt.Errorf("redis: addr is empty")
	}
	c := goredis.NewClient(&goredis.Options{
		Addr:        cfg.Addr,
		Password:    cfg.Password,
		DB:          cfg.DB,
		DialTimeout: 2 * time.Second,
		MaxRetries:  -1,
	})
	pingCtx, cancel := context.WithTimeout(ctx, 5*time.Second)
	defer cancel()
	if err := c.Ping(pingCtx).Err(); err != nil {
		_ = c.Close()
		return nil, fmt.Errorf("redis: ping: %w", err)
	}
	return c, nil
}
