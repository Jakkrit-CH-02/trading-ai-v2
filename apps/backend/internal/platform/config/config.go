package config

import (
	"fmt"
	"reflect"
	"strings"

	"github.com/mitchellh/mapstructure"
	"github.com/shopspring/decimal"
	"github.com/spf13/viper"
)

// Config is the root application configuration.
type Config struct {
	Server  ServerConfig  `mapstructure:"server"`
	Binance BinanceConfig `mapstructure:"binance"`
	DB      DBConfig      `mapstructure:"db"`
	Redis   RedisConfig   `mapstructure:"redis"`
	Risk    RiskConfig    `mapstructure:"risk"`
	AI      AIConfig      `mapstructure:"ai"`
	Auth    AuthConfig    `mapstructure:"auth"`
	Mode    string        `mapstructure:"mode"`
	Env     string        `mapstructure:"env"`
	Symbols []string      `mapstructure:"symbols"`
}

type AIConfig struct {
	BaseURL string `mapstructure:"base_url"`
}

type AuthConfig struct {
	JWTSecret string `mapstructure:"jwt_secret"`
	JWTTTLSec int    `mapstructure:"jwt_ttl_sec"`
}

type ServerConfig struct {
	Host string `mapstructure:"host"`
	Port int    `mapstructure:"port"`
}

type BinanceConfig struct {
	BaseURL   string `mapstructure:"base_url"`
	WSURL     string `mapstructure:"ws_url"`
	APIKey    string `mapstructure:"api_key"`
	APISecret string `mapstructure:"api_secret"`
	Testnet   bool   `mapstructure:"testnet"`
}

type DBConfig struct {
	DSN             string `mapstructure:"dsn"`
	MaxConns        int32  `mapstructure:"max_conns"`
	MinConns        int32  `mapstructure:"min_conns"`
	ConnMaxLifetime int    `mapstructure:"conn_max_lifetime_sec"`
}

type RedisConfig struct {
	Addr     string `mapstructure:"addr"`
	Password string `mapstructure:"password"`
	DB       int    `mapstructure:"db"`
}

type RiskConfig struct {
	MaxPositionPct      decimal.Decimal `mapstructure:"max_position_pct"`
	MaxDailyDrawdownPct decimal.Decimal `mapstructure:"max_daily_drawdown_pct"`
	MaxSlippageBps      int             `mapstructure:"max_slippage_bps"`
	RequireStopLoss     bool            `mapstructure:"require_stop_loss"`
}

// Load reads config from the given YAML path plus env overrides using prefix BOT_
// (e.g. BOT_RISK_MAX_POSITION_PCT=0.02).
func Load(path string) (Config, error) {
	v := viper.New()
	v.SetConfigFile(path)
	v.SetConfigType("yaml")

	v.SetEnvPrefix("BOT")
	v.SetEnvKeyReplacer(strings.NewReplacer(".", "_"))
	v.AutomaticEnv()

	setDefaults(v)

	if err := v.ReadInConfig(); err != nil {
		return Config{}, fmt.Errorf("config: read %s: %w", path, err)
	}

	var cfg Config
	if err := v.Unmarshal(&cfg, viper.DecodeHook(decimalHook())); err != nil {
		return Config{}, fmt.Errorf("config: unmarshal: %w", err)
	}
	if err := cfg.validate(); err != nil {
		return Config{}, fmt.Errorf("config: validate: %w", err)
	}
	return cfg, nil
}

func setDefaults(v *viper.Viper) {
	v.SetDefault("server.host", "0.0.0.0")
	v.SetDefault("server.port", 8080)
	v.SetDefault("env", "dev")
	v.SetDefault("mode", "paper")
	v.SetDefault("risk.max_position_pct", "0.02")
	v.SetDefault("risk.max_daily_drawdown_pct", "0.05")
	v.SetDefault("risk.max_slippage_bps", 30)
	v.SetDefault("risk.require_stop_loss", true)
	v.SetDefault("ai.base_url", "http://localhost:8001")
	v.SetDefault("auth.jwt_secret", "dev-secret-change-me")
	v.SetDefault("auth.jwt_ttl_sec", 86400)
	v.SetDefault("symbols", []string{"BTCUSDT"})
	v.SetDefault("db.max_conns", 10)
	v.SetDefault("db.min_conns", 1)
	v.SetDefault("db.conn_max_lifetime_sec", 1800)
}

func (c Config) validate() error {
	if c.Server.Port == 0 {
		return fmt.Errorf("server.port required")
	}
	if c.Risk.MaxPositionPct.Sign() <= 0 {
		return fmt.Errorf("risk.max_position_pct must be > 0")
	}
	if c.Risk.MaxDailyDrawdownPct.Sign() <= 0 {
		return fmt.Errorf("risk.max_daily_drawdown_pct must be > 0")
	}
	if c.Risk.MaxSlippageBps <= 0 {
		return fmt.Errorf("risk.max_slippage_bps must be > 0")
	}
	return nil
}

// decimalHook decodes strings and numbers into decimal.Decimal.
func decimalHook() mapstructure.DecodeHookFunc {
	decimalType := reflect.TypeOf(decimal.Decimal{})
	return func(from reflect.Type, to reflect.Type, data interface{}) (interface{}, error) {
		if to != decimalType {
			return data, nil
		}
		switch v := data.(type) {
		case string:
			return decimal.NewFromString(v)
		case float64:
			return decimal.NewFromFloat(v), nil
		case int:
			return decimal.NewFromInt(int64(v)), nil
		case int64:
			return decimal.NewFromInt(v), nil
		}
		return data, nil
	}
}
