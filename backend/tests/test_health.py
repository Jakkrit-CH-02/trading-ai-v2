from fastapi.testclient import TestClient

from app.core.logging import redact
from app.main import app


def test_health_returns_ok() -> None:
    res = TestClient(app).get("/health")
    assert res.status_code == 200
    assert res.json() == {"status": "ok"}


def test_log_redaction_masks_secrets() -> None:
    out = redact(None, "info", {"api_key": "abc", "api_secret": "def", "symbol": "BTCUSDT"})
    assert out == {"api_key": "***", "api_secret": "***", "symbol": "BTCUSDT"}
