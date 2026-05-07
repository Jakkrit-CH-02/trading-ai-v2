package integration

import (
	"context"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"testing"

	"github.com/stretchr/testify/require"

	"github.com/jakkrit-ch/trading-ai-v2/backend/internal/alert"
	"github.com/jakkrit-ch/trading-ai-v2/backend/internal/api"
	"github.com/jakkrit-ch/trading-ai-v2/backend/internal/platform/config"
)

func newAlertServer(t *testing.T) (*httptest.Server, *alert.Service, *alert.MemoryRepo) {
	t.Helper()
	repo := alert.NewMemoryRepo()
	svc := alert.NewService(repo, alert.StdoutNotifier{})
	cfg := config.Config{}
	cfg.Auth.JWTSecret = "test-secret"
	cfg.Auth.JWTTTLSec = 3600
	apiSrv := api.New(cfg, nil, nil, api.Options{Alerts: svc})
	srv := httptest.NewServer(apiSrv.Handler())
	t.Cleanup(srv.Close)
	return srv, svc, repo
}

type alertEnvelope struct {
	Data []struct {
		ID       string `json:"id"`
		Type     string `json:"type"`
		Severity string `json:"severity"`
		Message  string `json:"message"`
		Entity   string `json:"entity"`
		Read     bool   `json:"read"`
	} `json:"data"`
	Error interface{} `json:"error"`
}

func TestAlerts_EachRuleInsertsRow(t *testing.T) {
	_, svc, repo := newAlertServer(t)
	ctx := context.Background()

	cases := []struct {
		name string
		fn   func() (alert.Alert, error)
		want alert.Type
		sev  alert.Severity
	}{
		{"drawdown_breach", func() (alert.Alert, error) {
			return svc.DrawdownBreach(ctx, "BTCUSDT", "daily drawdown exceeded 5%")
		}, alert.TypeDrawdownBreach, alert.SeverityCritical},
		{"order_rejection", func() (alert.Alert, error) {
			return svc.OrderRejected(ctx, "ord_123", "risk_rejected: position too large")
		}, alert.TypeOrderRejection, alert.SeverityWarning},
		{"binance_disconnect", func() (alert.Alert, error) {
			return svc.BinanceDisconnected(ctx, "ws read: i/o timeout")
		}, alert.TypeBinanceDisconnect, alert.SeverityWarning},
		{"slippage_exceeded", func() (alert.Alert, error) {
			return svc.SlippageExceeded(ctx, "BTCUSDT", "slippage 45bps > 30bps")
		}, alert.TypeSlippageExceeded, alert.SeverityWarning},
		{"kill_triggered", func() (alert.Alert, error) {
			return svc.KillTriggered(ctx, "admin", "manual kill switch engaged")
		}, alert.TypeKillTriggered, alert.SeverityCritical},
	}

	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			before := repo.Count()
			a, err := tc.fn()
			require.NoError(t, err)
			require.NotEmpty(t, a.ID)
			require.Equal(t, tc.want, a.Type)
			require.Equal(t, tc.sev, a.Severity)
			require.False(t, a.Read)
			require.Equal(t, before+1, repo.Count())
		})
	}

	require.Equal(t, len(cases), repo.Count())
}

func TestAlerts_ListAndAck_HTTP(t *testing.T) {
	srv, svc, _ := newAlertServer(t)
	ctx := context.Background()
	tok := registerAndLogin(t, srv.URL, "alertop", "operator")

	a, err := svc.DrawdownBreach(ctx, "BTCUSDT", "daily drawdown exceeded 5%")
	require.NoError(t, err)
	_, err = svc.OrderRejected(ctx, "ord_999", "risk_rejected")
	require.NoError(t, err)

	resp := getURL(t, srv.URL+"/api/alerts", tok)
	require.Equal(t, http.StatusOK, resp.StatusCode)
	var list alertEnvelope
	require.NoError(t, json.NewDecoder(resp.Body).Decode(&list))
	resp.Body.Close()
	require.Len(t, list.Data, 2)
	// newest first
	require.Equal(t, "order_rejection", list.Data[0].Type)
	require.Equal(t, "drawdown_breach", list.Data[1].Type)

	resp = postJSON(t, srv.URL+"/api/alerts/"+a.ID+"/ack", tok, nil)
	require.Equal(t, http.StatusOK, resp.StatusCode)
	resp.Body.Close()

	resp = getURL(t, srv.URL+"/api/alerts", tok)
	require.Equal(t, http.StatusOK, resp.StatusCode)
	var after alertEnvelope
	require.NoError(t, json.NewDecoder(resp.Body).Decode(&after))
	resp.Body.Close()
	for _, item := range after.Data {
		if item.ID == a.ID {
			require.True(t, item.Read)
			return
		}
	}
	t.Fatalf("acked alert %s not found in list", a.ID)
}

func TestAlerts_AckUnknownReturns404(t *testing.T) {
	srv, _, _ := newAlertServer(t)
	tok := registerAndLogin(t, srv.URL, "alertop2", "operator")

	resp := postJSON(t, srv.URL+"/api/alerts/does-not-exist/ack", tok, nil)
	require.Equal(t, http.StatusNotFound, resp.StatusCode)
	resp.Body.Close()
}
