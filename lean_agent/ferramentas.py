"""Ferramentas que o agente e o nó de conversa podem chamar.

Por quê: o enunciado e o nome do arquivo vêm do estado do grafo (InjectedState) nas
ferramentas de verificação (`testar_tatica` e `testar_negacao`), nunca de argumentos
do modelo: se ele pudesse escolher o enunciado, poderia provar um teorema mais fácil
e receber ACEITA.
"""
from pathlib import Path
from typing import Annotated

from langchain_core.messages import ToolMessage
from langchain_core.tools import InjectedToolCallId, tool
from langgraph.prebuilt import InjectedState
from langgraph.types import Command

from .lean import negar_enunciado, test_prova
from .mcp_client import FERRAMENTAS_MCP
from .parser import parsear
from .rag import consultar_documentacao
from .skills import carregar_skill


@tool
def ler_guia_taticas() -> str:
    """Retorna o guia rápido de sintaxe e táticas básicas do Lean 4 em português."""
    caminho = Path("GuiaLean4.md")
    if caminho.exists():
        return caminho.read_text(encoding="utf-8")
    return "Guia não encontrado."


@tool(parse_docstring=True)
def testar_tatica(
    prova: str,
    enunciado: Annotated[str, InjectedState("enunciado")],
    nome_arquivo: Annotated[str, InjectedState("nome_arquivo")],
    tool_call_id: Annotated[str, InjectedToolCallId],
) -> Command:
    """Roda o Lean na sua prova do teorema atual e devolve ACEITA ou o erro, com hipóteses e objetivo.

    Args:
        prova: só as táticas que ficam depois do "by".
    """
    aceita, saida = test_prova(enunciado, prova, nome_arquivo)
    if aceita:
        erro = ""
        resposta = "ACEITA: o Lean aprovou a prova."
    else:
        log = parsear(saida)
        erro = log.get("mensagem_limpa") or saida.strip()[:300]
        resposta = (
            f"RECUSADA ({log.get('tipo', 'desconhecido')})\n"
            f"erro: {erro}\n"
            f"hipoteses: {log.get('hipoteses') or '(nenhuma)'}\n"
            f"objetivo: {log.get('objetivo') or '(nao extraido)'}\n"
            "Dica: se precisar, carregue a skill 'diagnostico_erros' ou consulte a documentação com 'consultar_documentacao'."
        )
    tentativa = {"prova": prova, "aceita": aceita, "erro": erro, "resposta": resposta}
    return Command(update={
        "tentativas": [tentativa],
        "rascunho": [ToolMessage(resposta, tool_call_id=tool_call_id)],
    })


@tool(parse_docstring=True)
def testar_negacao(
    prova: str,
    enunciado: Annotated[str, InjectedState("enunciado")],
    nome_arquivo: Annotated[str, InjectedState("nome_arquivo")],
    tool_call_id: Annotated[str, InjectedToolCallId],
) -> Command:
    """Roda o Lean na sua prova da NEGAÇÃO do teorema atual, quando ele parecer falso (contraexemplo).

    Args:
        prova: táticas depois do "by" para provar a negação (ex: 'intro h\\nexact absurd (h 0 1) (by decide)').
    """
    negacao = negar_enunciado(enunciado)
    aceita, saida = test_prova(negacao, prova, f"{nome_arquivo}_negacao")
    if aceita:
        resposta = f"ACEITA_NEGACAO: o Lean aprovou a refutação de {negacao}. O teorema original é FALSO."
        return Command(update={
            "negacao_aceita": prova,
            "rascunho": [ToolMessage(resposta, tool_call_id=tool_call_id)],
        })

    log = parsear(saida)
    erro = log.get("mensagem_limpa") or saida.strip()[:300]
    resposta = (
        f"RECUSADA ({log.get('tipo', 'desconhecido')}) ao provar {negacao}\n"
        f"erro: {erro}\n"
        f"hipoteses: {log.get('hipoteses') or '(nenhuma)'}\n"
        f"objetivo: {log.get('objetivo') or '(nao extraido)'}"
    )
    return Command(update={
        "rascunho": [ToolMessage(resposta, tool_call_id=tool_call_id)],
    })


# Ferramentas para o laço de conversa (RAG, Skills, MCP, guia) — sem `testar_tatica` que exige `enunciado`.
FERRAMENTAS_CONVERSA = [
    ler_guia_taticas,
    consultar_documentacao,
    carregar_skill,
] + FERRAMENTAS_MCP

# Ferramentas completas para o agente provador.
FERRAMENTAS = [
    testar_tatica,
    testar_negacao,
] + FERRAMENTAS_CONVERSA
