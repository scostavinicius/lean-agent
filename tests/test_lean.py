# Por quê: antes de medir o agente, provar que a régua funciona (aula 07). Se o
# Lean recusar uma prova de referência, o defeito está no harness (cabeçalho,
# definições), não no modelo.
import pytest

from lean_agent import lean
from lean_agent.casos import CASOS, PROVAS_REFERENCIA, REFUTACOES

from .conftest import requer_lean

pytestmark = requer_lean


def test_verificador_com_resultado_conhecido():
    assert lean.test_prova("(a b : Nat) : a + b = b + a", "omega")[0]
    aceita, saida = lean.test_prova("(a b : Nat) : a + b = b + a", "rfl")
    assert not aceita and "error" in saida
    assert not lean.test_prova("(a b : Nat) : a + b = b + a", "sorry")[0]


@pytest.mark.parametrize("caso", CASOS, ids=[c["nome"] for c in CASOS])
def test_referencia(caso):
    # Nos casos falsos, o Lean precisa aceitar a negação: é a garantia de que não existe prova.
    if caso["esperado"] == "provar":
        enunciado, prova = caso["enunciado"], PROVAS_REFERENCIA[caso["nome"]]
    else:
        enunciado, prova = REFUTACOES[caso["nome"]]
    aceita, saida = lean.test_prova(enunciado, prova, f"Ref{caso['nome']}")
    assert aceita, saida
