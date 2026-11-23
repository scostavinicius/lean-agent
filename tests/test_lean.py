# Por quê: antes de medir o agente, provar que a régua funciona (aula 07). Se o
# Lean recusar uma prova de referência, o defeito está no harness (cabeçalho,
# definições), não no modelo.
import httpx
import pytest

from lean_agent import lean, lean_web
from lean_agent.casos import CASOS, PROVAS_REFERENCIA, REFUTACOES

from .conftest import requer_lean


def test_execucao_web_normaliza_source_e_trata_timeout(monkeypatch):
    class _RespostaFalsa:
        def __init__(self, dados):
            self._dados = dados

        def raise_for_status(self):
            return None

        def json(self):
            return self._dados

    monkeypatch.setattr(
        lean_web.httpx,
        "post",
        lambda *args, **kwargs: _RespostaFalsa({
            "code": 1,
            "stdout": [{"text": "<source>:2:2: error: Tactic `rfl` failed"}],
            "stderr": [],
        }),
    )
    aceita, saida = lean.test_prova("(a b : Nat) : a + b = b + a", "rfl", "WebMock")
    assert not aceita
    assert saida.startswith("WebMock.lean:2:2: error:")

    def _timeout(*args, **kwargs):
        raise httpx.ReadTimeout("timeout")

    monkeypatch.setattr(lean_web.httpx, "post", _timeout)
    aceita_to, saida_to = lean.test_prova("(a b : Nat) : a + b = b + a", "omega", "WebTimeout")
    assert not aceita_to
    assert "passou de 60 s" in saida_to


@requer_lean
def test_verificador_com_resultado_conhecido():
    assert lean.test_prova("(a b : Nat) : a + b = b + a", "omega")[0]
    aceita, saida = lean.test_prova("(a b : Nat) : a + b = b + a", "rfl")
    assert not aceita and "error" in saida
    assert not lean.test_prova("(a b : Nat) : a + b = b + a", "sorry")[0]


@requer_lean
@pytest.mark.parametrize("caso", CASOS, ids=[c["nome"] for c in CASOS])
def test_referencia(caso):
    # Nos casos falsos, o Lean precisa aceitar a negação: é a garantia de que não existe prova.
    if caso["esperado"] == "provar":
        enunciado, prova = caso["enunciado"], PROVAS_REFERENCIA[caso["nome"]]
    else:
        enunciado, prova = REFUTACOES[caso["nome"]]
    aceita, saida = lean.test_prova(enunciado, prova, f"Ref{caso['nome']}")
    assert aceita, saida
