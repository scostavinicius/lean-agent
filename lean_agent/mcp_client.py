"""Cliente MCP real via protocolo stdio para o agente LangGraph.

Por quê: o requisito pede um servidor MCP desenvolvido pela dupla e um servidor MCP
da comunidade. Em vez de chamar funções Python direto em memória, este cliente abre
sessões reais do Model Context Protocol (`ClientSession` via `stdio_client`) para:
1. Servidor próprio da dupla (`lean_agent/mcp_server_proprio.py`)
2. Servidor oficial da comunidade (`mcp-server-fetch`: `python -m mcp_server_fetch`)
"""
import asyncio
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from langchain_core.tools import tool
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

_SERVIDOR_PROPRIO = str(Path(__file__).with_name("mcp_server_proprio.py"))

SERVIDORES_MCP = {
    "lean_proprio": StdioServerParameters(
        command=sys.executable,
        args=[_SERVIDOR_PROPRIO],
    ),
    "fetch_comunidade": StdioServerParameters(
        command=sys.executable,
        args=["-m", "mcp_server_fetch"],
    ),
}


def _executar_async(coro):
    """Executa corrotina mesmo se já houver loop ativo (Streamlit, Jupyter, Colab)."""
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro)
    with ThreadPoolExecutor(max_workers=1) as pool:
        return pool.submit(asyncio.run, coro).result()


async def _chamar_ferramenta_mcp(servidor: str, ferramenta: str, argumentos: dict) -> str:
    params = SERVIDORES_MCP[servidor]
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            resultado = await session.call_tool(ferramenta, argumentos)
            textos = [c.text for c in resultado.content if hasattr(c, "text") and c.text]
            return "\n".join(textos) if textos else "(sem retorno do servidor MCP)"


async def _listar_ferramentas_servidor(servidor: str) -> list[str]:
    params = SERVIDORES_MCP[servidor]
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            res = await session.list_tools()
            return [t.name for t in res.tools]


def descobrir_ferramentas_mcp() -> dict[str, list[str]]:
    """Consulta ao vivo os dois servidores MCP via stdio e lista suas ferramentas."""
    async def _descobrir():
        proprio = await _listar_ferramentas_servidor("lean_proprio")
        comunidade = await _listar_ferramentas_servidor("fetch_comunidade")
        return {"lean_proprio": proprio, "fetch_comunidade": comunidade}

    return _executar_async(_descobrir())


@tool(parse_docstring=True)
def mcp_lean_consultar(comando: str) -> str:
    """[MCP Próprio: lean-mcp-proprio] Executa no Lean 4 UM comando de consulta (#check, #print, #eval, #reduce).

    Args:
        comando: comando único começando com #check, #print, #eval ou #reduce (ex: '#check Nat.add_comm').
    """
    try:
        return _executar_async(_chamar_ferramenta_mcp("lean_proprio", "mcp_lean_consultar", {"comando": comando}))
    except Exception as erro:
        return f"ERRO MCP (lean-mcp-proprio): {type(erro).__name__}: {erro}"


@tool(parse_docstring=True)
def mcp_lean_analisar_teorema(enunciado: str) -> str:
    """[MCP Próprio: lean-mcp-proprio] Analisa quantificadores, tipos indutivos e funções do enunciado em Lean 4.

    Args:
        enunciado: enunciado formal do teorema em Lean 4.
    """
    try:
        return _executar_async(_chamar_ferramenta_mcp("lean_proprio", "mcp_lean_analisar_teorema", {"enunciado": enunciado}))
    except Exception as erro:
        return f"ERRO MCP (lean-mcp-proprio): {type(erro).__name__}: {erro}"


@tool(parse_docstring=True)
def mcp_lean_listar_definicoes() -> str:
    """[MCP Próprio: lean-mcp-proprio] Lista o código exato das definições recursivas (dobro, soma, rev) do projeto."""
    try:
        return _executar_async(_chamar_ferramenta_mcp("lean_proprio", "mcp_lean_listar_definicoes", {}))
    except Exception as erro:
        return f"ERRO MCP (lean-mcp-proprio): {type(erro).__name__}: {erro}"


@tool(parse_docstring=True)
def mcp_comunidade_fetch(url: str, max_length: int = 2500, start_index: int = 0) -> str:
    """[MCP Comunidade: mcp-server-fetch] Busca uma página da documentação oficial do Lean 4 / Mathlib na web e converte em Markdown.

    Use quando o RAG local não tiver detalhes suficientes ou quando o usuário pedir para consultar
    uma referência oficial online (ex: https://lean-lang.org/theorem_proving_in_lean4/Tactics/).

    Args:
        url: URL HTTP/HTTPS da documentação oficial a consultar.
        max_length: máximo de caracteres a retornar (padrão 2500 para caber no orçamento de tokens).
        start_index: deslocamento inicial para paginação em páginas longas.
    """
    try:
        return _executar_async(
            _chamar_ferramenta_mcp(
                "fetch_comunidade",
                "fetch",
                {"url": url, "max_length": max_length, "start_index": start_index},
            )
        )
    except Exception as erro:
        return f"ERRO MCP (mcp-server-fetch): {type(erro).__name__}: {erro}"


FERRAMENTAS_MCP_PROPRIO = [
    mcp_lean_consultar,
    mcp_lean_analisar_teorema,
    mcp_lean_listar_definicoes,
]

FERRAMENTAS_MCP_COMUNIDADE = [
    mcp_comunidade_fetch,
]

FERRAMENTAS_MCP = FERRAMENTAS_MCP_PROPRIO + FERRAMENTAS_MCP_COMUNIDADE
