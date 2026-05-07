package integration

import (
	"bytes"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"testing"

	"github.com/stretchr/testify/require"

	"github.com/jakkrit-ch/trading-ai-v2/backend/internal/api"
	"github.com/jakkrit-ch/trading-ai-v2/backend/internal/platform/config"
)

func newSettingsServer(t *testing.T) *httptest.Server {
	t.Helper()
	cfg := config.Config{}
	cfg.Auth.JWTSecret = "test-secret"
	cfg.Auth.JWTTTLSec = 3600
	apiSrv := api.New(cfg, nil, nil)
	srv := httptest.NewServer(apiSrv.Handler())
	t.Cleanup(srv.Close)
	return srv
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

func putJSON(t *testing.T, url, token string, body interface{}) *http.Response {
	t.Helper()
	buf, err := json.Marshal(body)
	require.NoError(t, err)
	req, err := http.NewRequest(http.MethodPut, url, bytes.NewReader(buf))
	require.NoError(t, err)
	req.Header.Set("Content-Type", "application/json")
	if token != "" {
		req.Header.Set("Authorization", "Bearer "+token)
	}
	resp, err := http.DefaultClient.Do(req)
	require.NoError(t, err)
	return resp
}

func registerAndLogin(t *testing.T, baseURL, user, role string) string {
	t.Helper()
	resp := postJSON(t, baseURL+"/api/auth/register", "", map[string]string{
		"username": user, "password": "supersecret", "role": role,
	})
	require.Equal(t, http.StatusCreated, resp.StatusCode)
	resp.Body.Close()
	return login(t, baseURL, user, "supersecret")
}

func TestSettings_RoundTrip_Operator(t *testing.T) {
	srv := newSettingsServer(t)
	tok := registerAndLogin(t, srv.URL, "op1", "operator")

	resp := getURL(t, srv.URL+"/api/settings", tok)
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
	resp = putJSON(t, srv.URL+"/api/settings", tok, body)
	require.Equal(t, http.StatusOK, resp.StatusCode)
	var put settingsEnvelope
	require.NoError(t, json.NewDecoder(resp.Body).Decode(&put))
	resp.Body.Close()
	require.Equal(t, "ETHUSDT", put.Data.DefaultSymbol)
	require.Equal(t, "0.01", put.Data.MaxPositionPct)
	require.True(t, put.Data.NotifyEmail)

	resp = getURL(t, srv.URL+"/api/settings", tok)
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
	srv := newSettingsServer(t)
	tok := registerAndLogin(t, srv.URL, "op2", "operator")

	body := map[string]interface{}{
		"default_symbol":         "ETHUSDT",
		"default_timeframe":      "bogus",
		"max_position_pct":       "0.01",
		"max_daily_drawdown_pct": "0.03",
		"max_slippage_bps":       50,
	}
	resp := putJSON(t, srv.URL+"/api/settings", tok, body)
	require.Equal(t, http.StatusBadRequest, resp.StatusCode)
	resp.Body.Close()

	body["default_timeframe"] = "1m"
	body["max_position_pct"] = "1.5"
	resp = putJSON(t, srv.URL+"/api/settings", tok, body)
	require.Equal(t, http.StatusBadRequest, resp.StatusCode)
	resp.Body.Close()
}

func TestSettings_RoleEnforcement(t *testing.T) {
	srv := newSettingsServer(t)

	adminTok := registerAndLogin(t, srv.URL, "settadmin", "admin")
	opTok := registerAndLogin(t, srv.URL, "settop", "operator")
	viewTok := registerAndLogin(t, srv.URL, "settview", "viewer")

	resp := getURL(t, srv.URL+"/api/auth/me", opTok)
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

	// Viewer cannot edit (operator-or-admin only for writes).
	resp = putJSON(t, srv.URL+"/api/settings", viewTok, body)
	require.Equal(t, http.StatusForbidden, resp.StatusCode)
	resp.Body.Close()

	// Viewer can read their own settings.
	resp = getURL(t, srv.URL+"/api/settings", viewTok)
	require.Equal(t, http.StatusOK, resp.StatusCode)
	resp.Body.Close()

	// Operator cannot edit another user's settings.
	resp = putJSON(t, srv.URL+"/api/settings?user_id=some-other-id", opTok, body)
	require.Equal(t, http.StatusForbidden, resp.StatusCode)
	resp.Body.Close()

	// Operator cannot read another user's settings.
	resp = getURL(t, srv.URL+"/api/settings?user_id=some-other-id", opTok)
	require.Equal(t, http.StatusForbidden, resp.StatusCode)
	resp.Body.Close()

	// Admin can edit the operator's settings.
	body["default_symbol"] = "SOLUSDT"
	resp = putJSON(t, srv.URL+"/api/settings?user_id="+opUserID, adminTok, body)
	require.Equal(t, http.StatusOK, resp.StatusCode)
	resp.Body.Close()

	// Operator now reads the admin-applied change.
	resp = getURL(t, srv.URL+"/api/settings", opTok)
	require.Equal(t, http.StatusOK, resp.StatusCode)
	var rt settingsEnvelope
	require.NoError(t, json.NewDecoder(resp.Body).Decode(&rt))
	resp.Body.Close()
	require.Equal(t, "SOLUSDT", rt.Data.DefaultSymbol)

	// Unauthenticated -> 401 from the auth middleware.
	resp = getURL(t, srv.URL+"/api/settings", "")
	require.Equal(t, http.StatusUnauthorized, resp.StatusCode)
	resp.Body.Close()
}
