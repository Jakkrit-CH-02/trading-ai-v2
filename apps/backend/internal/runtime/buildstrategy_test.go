package runtime

import (
	"testing"

	"github.com/stretchr/testify/require"
)

func TestBuildStrategy_MACross_defaults(t *testing.T) {
	s, err := buildStrategy("ma_cross", nil)
	require.NoError(t, err)
	require.NotNil(t, s)
	require.Equal(t, "ma_cross", s.Name())
}

func TestBuildStrategy_MACross_customParams(t *testing.T) {
	s, err := buildStrategy("ma_cross", map[string]string{"fast": "5", "slow": "15"})
	require.NoError(t, err)
	require.NotNil(t, s)
}

func TestBuildStrategy_RSI_defaults(t *testing.T) {
	s, err := buildStrategy("rsi", nil)
	require.NoError(t, err)
	require.NotNil(t, s)
	require.Equal(t, "rsi", s.Name())
}

func TestBuildStrategy_RSI_customParams(t *testing.T) {
	s, err := buildStrategy("rsi", map[string]string{
		"period":     "7",
		"oversold":   "25",
		"overbought": "75",
	})
	require.NoError(t, err)
	require.NotNil(t, s)
}

func TestBuildStrategy_RSI_invalidParams_fallsBackToDefault(t *testing.T) {
	s, err := buildStrategy("rsi", map[string]string{
		"period":   "not-a-number",
		"oversold": "bad",
	})
	require.NoError(t, err)
	require.NotNil(t, s)
}

func TestBuildStrategy_unknown(t *testing.T) {
	_, err := buildStrategy("nonexistent", nil)
	require.Error(t, err)
}
