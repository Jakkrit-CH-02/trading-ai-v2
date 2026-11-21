"""The AI layer cannot trade and cannot see exchange keys (SPEC 4 intro, SPEC 12).

Structural tests: they fail the build if someone wires a model's output to an order path or lets
the AI worker read secrets it must not have.
"""

import ast
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
AI_FILES = [*sorted((ROOT / "app" / "ai").glob("*.py")), ROOT / "services" / "ai_worker.py"]
FORBIDDEN_IMPORTS = (
    "app.execution",
    "app.exchange",
    "app.risk",
    "app.runtime",
    "app.bots",
    "app.auth",
    "app.backtest",
)


def imports(path: Path) -> list[str]:
    out: list[str] = []
    for node in ast.walk(ast.parse(path.read_text())):
        if isinstance(node, ast.Import):
            out += [a.name for a in node.names]
        elif isinstance(node, ast.ImportFrom) and node.module:
            out.append(node.module)
    return out


@pytest.mark.parametrize("path", AI_FILES, ids=lambda p: p.name)
def test_ai_code_has_no_import_path_to_orders_keys_or_the_risk_engine(path: Path) -> None:
    bad = [m for m in imports(path) if m.startswith(FORBIDDEN_IMPORTS)]
    assert not bad, f"{path.name} imports {bad}"


@pytest.mark.parametrize("path", AI_FILES, ids=lambda p: p.name)
def test_ai_code_never_reads_exchange_credentials(path: Path) -> None:
    src = path.read_text().lower()
    for secret in ("master_key", "binance_api", "api_secret", "api_key_enc", "totp"):
        assert secret not in src, f"{path.name} mentions {secret}"


def test_the_ai_worker_container_gets_no_exchange_keys_and_no_master_key() -> None:
    compose = (ROOT.parent / "docker-compose.yml").read_text()
    block = compose.split("  ai-worker:")[1].split("\n  api:")[0]
    assert "ANTHROPIC_API_KEY" in block
    for secret in ("MASTER_KEY", "BINANCE_API", "JWT_SECRET"):
        assert secret not in block


def test_only_the_ai_worker_container_receives_the_anthropic_key() -> None:
    compose = (ROOT.parent / "docker-compose.yml").read_text()
    for name in ("api", "runner", "market-data", "frontend"):
        part = compose.split(f"\n  {name}:")[1].split("\n  ")[0:1]
        service = compose.split(f"\n  {name}:")[1]
        service = service.split("\n\n")[0]
        assert "ANTHROPIC" not in service, f"{name} must not get the Anthropic key ({part})"
