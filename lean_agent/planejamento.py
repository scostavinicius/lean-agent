"""Planejamento: o modelo escreve o plano da prova antes da primeira tentativa.

O plano é saída estruturada (aula 03), validada pelo Pydantic, e entra no
pedido inicial do agente (aula 06).
"""
import logging

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import BaseModel

from .modelo import gerar_estruturado
from .prompts import PLANNER_SYSTEM

log = logging.getLogger(__name__)

MIN_PASSOS = 2


class Passo(BaseModel):
    instrucao: str
    tatica_provavel: str
    resultado_esperado: str


class Plano(BaseModel):
    passos: list[Passo]


def criar_plano(llm: BaseChatModel, enunciado: str) -> Plano | None:
    """Pede ao modelo o plano da prova. Devolve None se o modelo não colaborar."""
    mensagens = [
        SystemMessage(PLANNER_SYSTEM),
        HumanMessage(f"Planeje a prova do teorema em Lean 4: {enunciado}"),
    ]
    plano = gerar_estruturado(llm, mensagens, Plano)

    if plano is None:
        log.warning("sem plano: o laço segue apenas com o feedback do Lean")
        return None

    if len(plano.passos) < MIN_PASSOS:
        log.warning("plano com %d passo(s), abaixo do mínimo de %d; descartado", len(plano.passos), MIN_PASSOS)
        return None

    return plano


def formatar_plano(plano: Plano) -> str:
    """Escreve o plano como texto, para entrar no pedido ao agente."""
    linhas = [
        f"{numero}. {passo.instrucao} | tática provável: {passo.tatica_provavel}"
        f" | espera: {passo.resultado_esperado}"
        for numero, passo in enumerate(plano.passos, start=1)
    ]
    return (
        "PLANO DA PROVA (siga na ordem; se um passo se mostrar impossível, diga qual e "
        "proponha outro caminho):\n" + "\n".join(linhas)
    )
