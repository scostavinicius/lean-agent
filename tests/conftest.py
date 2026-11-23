import pytest

from lean_agent import lean
from lean_agent.lean_web import lean_web_disponivel

requer_lean = pytest.mark.skipif(
    not lean_web_disponivel(),
    reason="Lean 4 Web API indisponível ou LEAN_WEB_OFFLINE=1",
)


@pytest.fixture(autouse=True)
def workspace_temporario(tmp_path, monkeypatch):
    """Os .lean dos testes vão para uma pasta temporária, e não para workspace/."""
    monkeypatch.setattr(lean, "PASTA_LEAN", tmp_path)
