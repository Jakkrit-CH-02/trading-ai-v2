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

func newAuthServer(t *testing.T) *httptest.Server {
	t.Helper()
	cfg := config.Config{}
	cfg.Auth.JWTSecret = "test-secret"
	cfg.Auth.JWTTTLSec = 3600
	apiSrv := api.New(cfg, nil, nil)
	srv := httptest.NewServer(apiSrv.Handler())
	t.Cleanup(srv.Close)
	return srv
}

func postJSON(t *testing.T, url, token string, body interface{}) *http.Response {
	t.Helper()
	buf, err := json.Marshal(body)
	require.NoError(t, err)
	req, err := http.NewRequest(http.MethodPost, url, bytes.NewReader(buf))
	require.NoError(t, err)
	req.Header.Set("Content-Type", "application/json")
	if token != "" {
		req.Header.Set("Authorization", "Bearer "+token)
	}
	resp, err := http.DefaultClient.Do(req)
	require.NoError(t, err)
	return resp
}

func getURL(t *testing.T, url, token string) *http.Response {
	t.Helper()
	req, err := http.NewRequest(http.MethodGet, url, nil)
	require.NoError(t, err)
	if token != "" {
		req.Header.Set("Authorization", "Bearer "+token)
	}
	resp, err := http.DefaultClient.Do(req)
	require.NoError(t, err)
	return resp
}

func TestAuth_RegisterAndLogin(t *testing.T) {
	srv := newAuthServer(t)

	// Register a viewer.
	resp := postJSON(t, srv.URL+"/api/auth/register", "", map[string]string{
		"username": "alice",
		"password": "supersecret",
		"role":     "viewer",
	})
	require.Equal(t, http.StatusCreated, resp.StatusCode)
	resp.Body.Close()

	// Duplicate registration -> 409.
	resp = postJSON(t, srv.URL+"/api/auth/register", "", map[string]string{
		"username": "alice",
		"password": "supersecret",
		"role":     "viewer",
	})
	require.Equal(t, http.StatusConflict, resp.StatusCode)
	resp.Body.Close()

	// Login OK.
	resp = postJSON(t, srv.URL+"/api/auth/login", "", map[string]string{
		"username": "alice",
		"password": "supersecret",
	})
	require.Equal(t, http.StatusOK, resp.StatusCode)
	var env struct {
		Data struct {
			Token string `json:"token"`
			User  struct {
				ID       string `json:"id"`
				Username string `json:"username"`
				Role     string `json:"role"`
			} `json:"user"`
		} `json:"data"`
		Error interface{} `json:"error"`
	}
	require.NoError(t, json.NewDecoder(resp.Body).Decode(&env))
	resp.Body.Close()
	require.NotEmpty(t, env.Data.Token)
	require.Equal(t, "alice", env.Data.User.Username)
	require.Equal(t, "viewer", env.Data.User.Role)

	// Bad password -> 401.
	resp = postJSON(t, srv.URL+"/api/auth/login", "", map[string]string{
		"username": "alice",
		"password": "wrongpass",
	})
	require.Equal(t, http.StatusUnauthorized, resp.StatusCode)
	resp.Body.Close()

	// Protected /api/auth/me without token -> 401.
	resp = getURL(t, srv.URL+"/api/auth/me", "")
	require.Equal(t, http.StatusUnauthorized, resp.StatusCode)
	resp.Body.Close()

	// /api/auth/me with token -> 200 + user.
	resp = getURL(t, srv.URL+"/api/auth/me", env.Data.Token)
	require.Equal(t, http.StatusOK, resp.StatusCode)
	var meEnv struct {
		Data struct {
			Username string `json:"username"`
			Role     string `json:"role"`
		} `json:"data"`
	}
	require.NoError(t, json.NewDecoder(resp.Body).Decode(&meEnv))
	resp.Body.Close()
	require.Equal(t, "alice", meEnv.Data.Username)
	require.Equal(t, "viewer", meEnv.Data.Role)
}

func TestAuth_RoleGuard_AdminOnlyRoute(t *testing.T) {
	srv := newAuthServer(t)

	// Register a viewer and an admin.
	resp := postJSON(t, srv.URL+"/api/auth/register", "", map[string]string{
		"username": "viewer1", "password": "supersecret", "role": "viewer",
	})
	require.Equal(t, http.StatusCreated, resp.StatusCode)
	resp.Body.Close()

	resp = postJSON(t, srv.URL+"/api/auth/register", "", map[string]string{
		"username": "admin1", "password": "supersecret", "role": "admin",
	})
	require.Equal(t, http.StatusCreated, resp.StatusCode)
	resp.Body.Close()

	viewerTok := login(t, srv.URL, "viewer1", "supersecret")
	adminTok := login(t, srv.URL, "admin1", "supersecret")

	// Viewer hitting admin route -> 403.
	resp = postJSON(t, srv.URL+"/api/admin/users", viewerTok, map[string]string{
		"username": "newbie", "password": "supersecret", "role": "viewer",
	})
	require.Equal(t, http.StatusForbidden, resp.StatusCode)
	resp.Body.Close()

	// Admin hitting admin route -> 201.
	resp = postJSON(t, srv.URL+"/api/admin/users", adminTok, map[string]string{
		"username": "newbie", "password": "supersecret", "role": "viewer",
	})
	require.Equal(t, http.StatusCreated, resp.StatusCode)
	resp.Body.Close()
}

func TestAuth_InvalidToken(t *testing.T) {
	srv := newAuthServer(t)
	resp := getURL(t, srv.URL+"/api/auth/me", "garbage.not.a.jwt")
	require.Equal(t, http.StatusUnauthorized, resp.StatusCode)
	resp.Body.Close()
}

func login(t *testing.T, baseURL, user, pass string) string {
	t.Helper()
	resp := postJSON(t, baseURL+"/api/auth/login", "", map[string]string{
		"username": user, "password": pass,
	})
	require.Equal(t, http.StatusOK, resp.StatusCode)
	var env struct {
		Data struct {
			Token string `json:"token"`
		} `json:"data"`
	}
	require.NoError(t, json.NewDecoder(resp.Body).Decode(&env))
	resp.Body.Close()
	return env.Data.Token
}
