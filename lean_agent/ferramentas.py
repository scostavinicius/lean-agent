"""Ferramentas que o agente pode chamar.

O enunciado e o nome do arquivo vêm do estado do grafo (InjectedState), e não
dos argumentos que o modelo escreve: se o modelo pudesse escolher o enunciado,
poderia testar um teorema mais fácil e receber ACEITA.
"""
from pathlib import Path
from typing import Annotated

from langchain_core.messages import ToolMessage
from langchain_core.tools import InjectedToolCallId, tool
from langgraph.prebuilt import InjectedState
from langgraph.types import Command

from .lean import test_prova
from .parser import parsear


# Por quê: o modelo consulta a sintaxe das táticas quando está em dúvida, em vez
# de inventar. O texto vem do GuiaLean4.md do repositório.
@tool
def ler_guia_taticas() -> str:
    """Retorna o guia rápido de sintaxe e táticas básicas do Lean 4."""
    caminho = Path("GuiaLean4.md")
    if caminho.exists():
        return caminho.read_text(encoding="utf-8")
    return "Guia não encontrado."


# Por quê: roda o Lean uma vez por chamada e devolve o erro já analisado. Como
# não há laço aqui dentro, é o modelo quem decide tentar de novo (ReAct, aula 06).
# Cada chamada vira uma entrada em `tentativas` no estado, e é por ali que o
# grafo sabe se a prova foi aceita.
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
            f"objetivo: {log.get('objetivo') or '(nao extraido)'}"
        )
    tentativa = {"prova": prova, "aceita": aceita, "erro": erro, "resposta": resposta}
    return Command(update={
        "tentativas": [tentativa],
        "rascunho": [ToolMessage(resposta, tool_call_id=tool_call_id)],
    })


FERRAMENTAS = [ler_guia_taticas, testar_tatica]
