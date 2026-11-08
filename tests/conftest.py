import shutil

import pytest

from lean_agent import lean

requer_lean = pytest.mark.skipif(shutil.which("lean") is None, reason="Lean não instalado (veja o README)")


@pytest.fixture(autouse=True)
def workspace_temporario(tmp_path, monkeypatch):
    """Os .lean dos testes vão para uma pasta temporária, e não para workspace/."""
    monkeypatch.setattr(lean, "PASTA_LEAN", tmp_path)
