package integration

import (
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"testing"

	"github.com/stretchr/testify/require"

	"github.com/jakkrit-ch/trading-ai-v2/backend/internal/api"
	"github.com/jakkrit-ch/trading-ai-v2/backend/internal/platform/config"
)

// envelope mirrors the wire contract documented in internal/api/response.go.
// Using map[string]json.RawMessage lets us verify exact field presence
// (e.g. "error": null literal) rather than just non-nilness.
type envelope struct {
	Data  json.RawMessage `json:"data"`
	Error *struct {
		Code    string          `json:"code"`
		Message string          `json:"message"`
		Details json.RawMessage `json:"details,omitempty"`
	} `json:"error"`
}

func newTestServer(t *testing.T) *httptest.Server {
	t.Helper()
	srv := httptest.NewServer(api.New(config.Config{}, nil, nil).Handler())
	t.Cleanup(srv.Close)
	return srv
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
	body, err := json.Marshal(raw)
	require.NoError(t, err)
	require.NoError(t, json.Unmarshal(body, &env))
	return env, raw
}

func TestEnvelope_HealthzSuccess(t *testing.T) {
	srv := newTestServer(t)

	resp, err := http.Get(srv.URL + "/healthz")
	require.NoError(t, err)

	require.Equal(t, http.StatusOK, resp.StatusCode)
	require.Equal(t, "application/json; charset=utf-8", resp.Header.Get("Content-Type"))

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
	srv := newTestServer(t)

	req, err := http.NewRequest(http.MethodGet, srv.URL+"/debug/error", nil)
	require.NoError(t, err)
	req.Header.Set("Authorization", "Bearer dev")

	resp, err := http.DefaultClient.Do(req)
	require.NoError(t, err)

	require.Equal(t, http.StatusTeapot, resp.StatusCode)
	require.Equal(t, "application/json; charset=utf-8", resp.Header.Get("Content-Type"))

	env, raw := decodeEnvelope(t, resp)

	require.JSONEq(t, `null`, string(raw["data"]), "error envelope must have data: null")
	require.NotNil(t, env.Error)
	require.NotEmpty(t, env.Error.Code, "error.code must be a non-empty stable string")
	require.NotEmpty(t, env.Error.Message)
	require.Equal(t, "debug_forced_error", env.Error.Code)
	require.NotNil(t, env.Error.Details, "details should be present when set by handler")
}

func TestEnvelope_AuthFailureShape(t *testing.T) {
	// A protected route hit without the bearer must still return the error envelope.
	srv := newTestServer(t)

	resp, err := http.Get(srv.URL + "/debug/error")
	require.NoError(t, err)

	require.Equal(t, http.StatusUnauthorized, resp.StatusCode)
	env, raw := decodeEnvelope(t, resp)

	require.JSONEq(t, `null`, string(raw["data"]))
	require.NotNil(t, env.Error)
	require.Equal(t, "forbidden", env.Error.Code)
}
