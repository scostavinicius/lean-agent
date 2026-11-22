"""Servidor MCP próprio do assistente em Lean 4 (desenvolvido pela dupla).

Por quê: expõe ferramentas específicas do domínio de verificação formal pelo
protocolo padrão MCP (stdio ou streamable-http), permitindo que qualquer cliente
MCP (ou nosso grafo LangGraph) inspecione tipos, definições e estrutura de teoremas.

Como iniciar manualmente:
    python lean_agent/mcp_server_proprio.py
"""
import argparse
import asyncio
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

from mcp.server.mcpserver import MCPServer

# Garante importação limpa mesmo quando executado como script standalone
_RAIZ = Path(__file__).resolve().parent.parent
if str(_RAIZ) not in sys.path:
    sys.path.insert(0, str(_RAIZ))

# Evita acionar lean_agent/__init__.py se executado diretamente
if shutil.which("lean") is None:
    os.environ["PATH"] = os.path.expanduser("~/.elan/bin") + os.pathsep + os.environ["PATH"]

PASTA_LEAN = Path("workspace")
TIMEOUT_LEAN = 60

DEFINICOES_LEAN = """def dobro : Nat → Nat
  | 0     => 0
  | n + 1 => dobro n + 2

def soma : Nat → Nat
  | 0     => 0
  | n + 1 => soma n + (n + 1)

def rev {α : Type} : List α → List α
  | []      => []
  | x :: xs => rev xs ++ [x]"""

COMANDOS_CONSULTA = ("#check", "#print", "#eval", "#reduce")
PROIBIDO_EM_CONSULTA = re.compile(r"\b(IO|System|Process|FS|unsafe)\b")

mcp_proprio = MCPServer("lean-mcp-proprio", version="1.0.0")


@mcp_proprio.tool(
    name="mcp_lean_consultar",
    description="Roda no compilador Lean 4 UM comando de consulta (#check, #print, #eval ou #reduce) e devolve a resposta.",
)
def lean_consultar(comando: str) -> str:
    """Executa uma consulta segura de tipo ou definição diretamente no Lean 4."""
    comando = comando.strip()
    if "\n" in comando or not comando.startswith(COMANDOS_CONSULTA):
        return f"RECUSADO: envie um único comando que comece com {', '.join(COMANDOS_CONSULTA)}."
    if PROIBIDO_EM_CONSULTA.search(comando):
        return "RECUSADO: consultas não podem usar IO, System, Process, FS nem unsafe."

    if shutil.which("lean") is None:
        return (
            "ERRO: compilador Lean 4 ('lean') não encontrado no PATH nem em ~/.elan/bin. "
            "Instale pelo elan (veja o README) ou execute no Google Colab."
        )

    PASTA_LEAN.mkdir(exist_ok=True)
    arquivo = PASTA_LEAN / "Consulta_MCP.lean"
    arquivo.write_text(f"{DEFINICOES_LEAN}\n\n{comando}\n", encoding="utf-8")

    try:
        resultado = subprocess.run(
            ["lean", arquivo.name],
            cwd=PASTA_LEAN,
            capture_output=True,
            text=True,
            timeout=TIMEOUT_LEAN,
            encoding="utf-8",
            errors="replace",
        )
    except subprocess.TimeoutExpired:
        return f"ERRO: o Lean passou de {TIMEOUT_LEAN} s nessa consulta."

    saida = re.sub(
        r"^\S*Consulta_MCP\.lean:\d+:\d+:\s*(info:\s*)?",
        "",
        resultado.stdout + resultado.stderr,
        flags=re.MULTILINE,
    )
    return (saida.strip() or "(o Lean não imprimiu nada)")[:800]


@mcp_proprio.tool(
    name="mcp_lean_analisar_teorema",
    description="Analisa a estrutura formal de um enunciado em Lean 4 e recomenda estratégia e skills.",
)
def lean_analisar_teorema(enunciado: str) -> str:
    """Classifica quantificadores, tipos indutivos e funções recursivas no enunciado."""
    enunciado = enunciado.strip()
    quant_univ = len(re.findall(r"∀|\bforall\b", enunciado))
    quant_exist = len(re.findall(r"∃|\bexists\b", enunciado))
    funcoes_recursivas = [fn for fn in ("dobro", "soma", "rev") if re.search(rf"\b{fn}\b", enunciado)]
    tipos_indutivos = [tp for tp in ("Nat", "List") if re.search(rf"\b{tp}\b", enunciado)]

    if funcoes_recursivas:
        dificuldade = "Alta (indutiva com definição recursiva)"
        recomendacao = (
            f"Envolve função recursiva ({', '.join(funcoes_recursivas)}). "
            "Carregue a skill `inducao_estruturada` antes de propor a prova."
        )
    elif tipos_indutivos and ("+" in enunciado or "<" in enunciado or "≤" in enunciado or "≥" in enunciado):
        dificuldade = "Média (aritmética ou ordem em tipos indutivos)"
        recomendacao = (
            "Teste aritmética linear com `omega`, ou `simp` / `induction` com lemas de `Nat`. "
            "Se suspeitar que é falso, tente contraexemplo em `testar_negacao`."
        )
    elif quant_exist > 0:
        dificuldade = "Média (quantificador existencial)"
        recomendacao = "Forneça a testemunha explícita com `exact ⟨valor, rfl⟩` ou `refine ⟨valor, ?_⟩`."
    else:
        dificuldade = "Básica (lógica proposicional / igualdade)"
        recomendacao = "Use `intro`, `exact`, `cases` ou `rfl`."

    return (
        f"Análise estrutural de `{enunciado}`:\n"
        f"- Quantificadores: ∀={quant_univ}, ∃={quant_exist}\n"
        f"- Tipos indutivos: {', '.join(tipos_indutivos) or 'nenhum'}\n"
        f"- Funções do projeto: {', '.join(funcoes_recursivas) or 'nenhuma'}\n"
        f"- Complexidade: {dificuldade}\n"
        f"- Estratégia sugerida: {recomendacao}"
    )


@mcp_proprio.tool(
    name="mcp_lean_listar_definicoes",
    description="Lista o código exato das definições recursivas (dobro, soma, rev) carregadas no ambiente Lean 4.",
)
def lean_listar_definicoes() -> str:
    """Devolve as definições Lean 4 injetadas no cabeçalho de verificação."""
    return f"Definições carregadas no escopo padrão do projeto:\n\n```lean\n{DEFINICOES_LEAN}\n```"


def main() -> None:
    parser = argparse.ArgumentParser(description="Servidor MCP próprio para Lean 4")
    parser.add_argument("--transporte", choices=["stdio", "streamable-http"], default="stdio")
    args = parser.parse_args()
    if args.transporte == "streamable-http":
        mcp_proprio.run(transport="streamable-http")
    else:
        asyncio.run(mcp_proprio.run_stdio_async())


if __name__ == "__main__":
    main()
