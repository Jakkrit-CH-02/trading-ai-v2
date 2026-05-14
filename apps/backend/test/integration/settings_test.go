package integration

import (
	"encoding/json"
	"net/http"
	"testing"

	"github.com/gofiber/fiber/v2"
	"github.com/stretchr/testify/require"

	"github.com/jakkrit-ch/trading-ai-v2/backend/internal/api"
	"github.com/jakkrit-ch/trading-ai-v2/backend/internal/platform/config"
)

func newSettingsApp(t *testing.T) *fiber.App {
	t.Helper()
	cfg := config.Config{}
	cfg.Auth.JWTSecret = "test-secret"
	cfg.Auth.JWTTTLSec = 3600
	return api.New(cfg, nil, nil).App()
}

type settingsEnvelope struct {
	Data struct {
		UserID              string `json:"user_id"`
		DefaultSymbol       string `json:"default_symbol"`
		DefaultTimeframe    string `json:"default_timeframe"`
		MaxPositionPct      string `json:"max_position_pct"`
		MaxDailyDrawdownPct string `json:"max_daily_drawdown_pct"`
		MaxSlippageBps      int    `json:"max_slippage_bps"`
		NotifyEmail         bool   `json:"notify_email"`
		NotifyWebhookURL    string `json:"notify_webhook_url"`
	} `json:"data"`
	Error interface{} `json:"error"`
}

func TestSettings_RoundTrip_Operator(t *testing.T) {
	app := newSettingsApp(t)
	tok := registerAndLogin(t, app, "op1", "operator")

	resp := getURL(t, app, "/api/settings", tok)
	require.Equal(t, http.StatusOK, resp.StatusCode)
	var got settingsEnvelope
	require.NoError(t, json.NewDecoder(resp.Body).Decode(&got))
	resp.Body.Close()
	require.Equal(t, "BTCUSDT", got.Data.DefaultSymbol)
	require.Equal(t, "1m", got.Data.DefaultTimeframe)
	require.Equal(t, "0.02", got.Data.MaxPositionPct)
	require.Equal(t, 30, got.Data.MaxSlippageBps)

	body := map[string]interface{}{
		"default_symbol":         "ETHUSDT",
		"default_timeframe":      "5m",
		"max_position_pct":       "0.01",
		"max_daily_drawdown_pct": "0.03",
		"max_slippage_bps":       50,
		"notify_email":           true,
		"notify_webhook_url":     "https://example.com/hook",
	}
	resp = putJSON(t, app, "/api/settings", tok, body)
	require.Equal(t, http.StatusOK, resp.StatusCode)
	var put settingsEnvelope
	require.NoError(t, json.NewDecoder(resp.Body).Decode(&put))
	resp.Body.Close()
	require.Equal(t, "ETHUSDT", put.Data.DefaultSymbol)
	require.Equal(t, "0.01", put.Data.MaxPositionPct)
	require.True(t, put.Data.NotifyEmail)

	resp = getURL(t, app, "/api/settings", tok)
	require.Equal(t, http.StatusOK, resp.StatusCode)
	var rt settingsEnvelope
	require.NoError(t, json.NewDecoder(resp.Body).Decode(&rt))
	resp.Body.Close()
	require.Equal(t, "ETHUSDT", rt.Data.DefaultSymbol)
	require.Equal(t, "5m", rt.Data.DefaultTimeframe)
	require.Equal(t, "0.03", rt.Data.MaxDailyDrawdownPct)
	require.Equal(t, 50, rt.Data.MaxSlippageBps)
	require.Equal(t, "https://example.com/hook", rt.Data.NotifyWebhookURL)
}

func TestSettings_Validation_Rejects(t *testing.T) {
	app := newSettingsApp(t)
	tok := registerAndLogin(t, app, "op2", "operator")

	body := map[string]interface{}{
		"default_symbol":         "ETHUSDT",
		"default_timeframe":      "bogus",
		"max_position_pct":       "0.01",
		"max_daily_drawdown_pct": "0.03",
		"max_slippage_bps":       50,
	}
	resp := putJSON(t, app, "/api/settings", tok, body)
	require.Equal(t, http.StatusBadRequest, resp.StatusCode)
	resp.Body.Close()

	body["default_timeframe"] = "1m"
	body["max_position_pct"] = "1.5"
	resp = putJSON(t, app, "/api/settings", tok, body)
	require.Equal(t, http.StatusBadRequest, resp.StatusCode)
	resp.Body.Close()
}

func TestSettings_RoleEnforcement(t *testing.T) {
	app := newSettingsApp(t)

	adminTok := registerAndLogin(t, app, "settadmin", "admin")
	opTok := registerAndLogin(t, app, "settop", "operator")
	viewTok := registerAndLogin(t, app, "settview", "viewer")

	resp := getURL(t, app, "/api/auth/me", opTok)
	require.Equal(t, http.StatusOK, resp.StatusCode)
	var me struct {
		Data struct {
			ID string `json:"id"`
		} `json:"data"`
	}
	require.NoError(t, json.NewDecoder(resp.Body).Decode(&me))
	resp.Body.Close()
	opUserID := me.Data.ID
	require.NotEmpty(t, opUserID)

	body := map[string]interface{}{
		"default_symbol":         "BTCUSDT",
		"default_timeframe":      "1m",
		"max_position_pct":       "0.02",
		"max_daily_drawdown_pct": "0.05",
		"max_slippage_bps":       30,
	}

	// Viewer cannot edit.
	resp = putJSON(t, app, "/api/settings", viewTok, body)
	require.Equal(t, http.StatusForbidden, resp.StatusCode)
	resp.Body.Close()

	// Viewer can read their own settings.
	resp = getURL(t, app, "/api/settings", viewTok)
	require.Equal(t, http.StatusOK, resp.StatusCode)
	resp.Body.Close()

	// Operator cannot edit another user's settings.
	resp = putJSON(t, app, "/api/settings?user_id=some-other-id", opTok, body)
	require.Equal(t, http.StatusForbidden, resp.StatusCode)
	resp.Body.Close()

	// Operator cannot read another user's settings.
	resp = getURL(t, app, "/api/settings?user_id=some-other-id", opTok)
	require.Equal(t, http.StatusForbidden, resp.StatusCode)
	resp.Body.Close()

	// Admin can edit the operator's settings.
	body["default_symbol"] = "SOLUSDT"
	resp = putJSON(t, app, "/api/settings?user_id="+opUserID, adminTok, body)
	require.Equal(t, http.StatusOK, resp.StatusCode)
	resp.Body.Close()

	// Operator now reads the admin-applied change.
	resp = getURL(t, app, "/api/settings", opTok)
	require.Equal(t, http.StatusOK, resp.StatusCode)
	var rt settingsEnvelope
	require.NoError(t, json.NewDecoder(resp.Body).Decode(&rt))
	resp.Body.Close()
	require.Equal(t, "SOLUSDT", rt.Data.DefaultSymbol)

	// Unauthenticated -> 401 from the auth middleware.
	resp = getURL(t, app, "/api/settings", "")
	require.Equal(t, http.StatusUnauthorized, resp.StatusCode)
	resp.Body.Close()
}
