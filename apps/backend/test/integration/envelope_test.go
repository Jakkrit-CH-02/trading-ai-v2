package integration

import (
	"bytes"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"testing"

	"github.com/gofiber/fiber/v2"
	"github.com/stretchr/testify/require"

	"github.com/jakkrit-ch/trading-ai-v2/backend/internal/api"
	"github.com/jakkrit-ch/trading-ai-v2/backend/internal/auth"
	"github.com/jakkrit-ch/trading-ai-v2/backend/internal/platform/config"
)

// envelope mirrors the wire contract documented in internal/api/response.go.
type envelope struct {
	Data  json.RawMessage `json:"data"`
	Error *struct {
		Code    string          `json:"code"`
		Message string          `json:"message"`
		Details json.RawMessage `json:"details,omitempty"`
	} `json:"error"`
}

func newTestApp(t *testing.T) *fiber.App {
	t.Helper()
	a, _ := newTestAppWithAuth(t)
	return a
}

// newTestAppWithAuth returns a Fiber app plus a valid bearer token for an admin user.
func newTestAppWithAuth(t *testing.T) (*fiber.App, string) {
	t.Helper()
	cfg := config.Config{}
	cfg.Auth.JWTSecret = "test-secret"
	cfg.Auth.JWTTTLSec = 3600
	apiSrv := api.New(cfg, nil, nil)
	app := apiSrv.App()
	if _, err := apiSrv.AuthService().Register(t.Context(), "tester", "password123", auth.RoleAdmin); err != nil {
		t.Fatalf("register tester: %v", err)
	}
	tok, _, err := apiSrv.AuthService().Login(t.Context(), "tester", "password123")
	if err != nil {
		t.Fatalf("login tester: %v", err)
	}
	return app, tok
}

func postJSON(t *testing.T, app *fiber.App, path, token string, body interface{}) *http.Response {
	t.Helper()
	buf, err := json.Marshal(body)
	require.NoError(t, err)
	req := httptest.NewRequest(http.MethodPost, path, bytes.NewReader(buf))
	req.Header.Set("Content-Type", "application/json")
	if token != "" {
		req.Header.Set("Authorization", "Bearer "+token)
	}
	resp, err := app.Test(req, -1)
	require.NoError(t, err)
	return resp
}

func getURL(t *testing.T, app *fiber.App, path, token string) *http.Response {
	t.Helper()
	req := httptest.NewRequest(http.MethodGet, path, nil)
	if token != "" {
		req.Header.Set("Authorization", "Bearer "+token)
	}
	resp, err := app.Test(req, -1)
	require.NoError(t, err)
	return resp
}

func putJSON(t *testing.T, app *fiber.App, path, token string, body interface{}) *http.Response {
	t.Helper()
	buf, err := json.Marshal(body)
	require.NoError(t, err)
	req := httptest.NewRequest(http.MethodPut, path, bytes.NewReader(buf))
	req.Header.Set("Content-Type", "application/json")
	if token != "" {
		req.Header.Set("Authorization", "Bearer "+token)
	}
	resp, err := app.Test(req, -1)
	require.NoError(t, err)
	return resp
}

func decodeEnvelope(t *testing.T, resp *http.Response) (envelope, map[string]json.RawMessage) {
	t.Helper()
	defer resp.Body.Close()

	var raw map[string]json.RawMessage
	require.NoError(t, json.NewDecoder(resp.Body).Decode(&raw))

	require.Contains(t, raw, "data", "envelope must have a top-level data key")
	require.Contains(t, raw, "error", "envelope must have a top-level error key")
	require.Len(t, raw, 2, "envelope must contain exactly data and error keys, got %v", raw)

	var env envelope
	b, err := json.Marshal(raw)
	require.NoError(t, err)
	require.NoError(t, json.Unmarshal(b, &env))
	return env, raw
}

func TestEnvelope_HealthzSuccess(t *testing.T) {
	app := newTestApp(t)

	resp, err := app.Test(httptest.NewRequest(http.MethodGet, "/healthz", nil), -1)
	require.NoError(t, err)

	require.Equal(t, http.StatusOK, resp.StatusCode)
	require.Equal(t, "application/json", resp.Header.Get("Content-Type"))

	env, raw := decodeEnvelope(t, resp)

	require.Nil(t, env.Error, "success envelope must have error: null")
	require.JSONEq(t, `null`, string(raw["error"]))

	var data struct {
		Status string `json:"status"`
		Deps   struct {
			Postgres string `json:"postgres"`
			Redis    string `json:"redis"`
		} `json:"deps"`
	}
	require.NoError(t, json.Unmarshal(env.Data, &data))
	require.NotEmpty(t, data.Status)
	require.Contains(t, []string{"up", "down"}, data.Deps.Postgres)
	require.Contains(t, []string{"up", "down"}, data.Deps.Redis)
}

func TestEnvelope_DebugErrorFailure(t *testing.T) {
	app, tok := newTestAppWithAuth(t)

	req := httptest.NewRequest(http.MethodGet, "/debug/error", nil)
	req.Header.Set("Authorization", "Bearer "+tok)

	resp, err := app.Test(req, -1)
	require.NoError(t, err)

	require.Equal(t, http.StatusTeapot, resp.StatusCode)

	env, raw := decodeEnvelope(t, resp)

	require.JSONEq(t, `null`, string(raw["data"]), "error envelope must have data: null")
	require.NotNil(t, env.Error)
	require.NotEmpty(t, env.Error.Code, "error.code must be a non-empty stable string")
	require.NotEmpty(t, env.Error.Message)
	require.Equal(t, "debug_forced_error", env.Error.Code)
	require.NotNil(t, env.Error.Details, "details should be present when set by handler")
}

func TestEnvelope_AuthFailureShape(t *testing.T) {
	app := newTestApp(t)

	resp, err := app.Test(httptest.NewRequest(http.MethodGet, "/debug/error", nil), -1)
	require.NoError(t, err)

	require.Equal(t, http.StatusUnauthorized, resp.StatusCode)
	env, raw := decodeEnvelope(t, resp)

	require.JSONEq(t, `null`, string(raw["data"]))
	require.NotNil(t, env.Error)
	require.Equal(t, "unauthorized", env.Error.Code)
}
