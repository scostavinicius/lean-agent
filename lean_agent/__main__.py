"""Linha de comando: rodar os casos de teste, conversar no terminal ou desenhar o grafo.

    python -m lean_agent casos                  # os 10 casos da Unidade II, com a tabela
    python -m lean_agent casos TESTE1_RAG       # um caso específico, com rastro
    python -m lean_agent chat                   # conversa numa thread, com memória entre turnos
    python -m lean_agent grafo                  # o diagrama Mermaid do grafo
"""
import argparse
import logging
import sys
import uuid

from langchain_core.messages import HumanMessage

from .avaliacao import rodar_todos_casos, tabela_markdown_unidade2
from .grafo import criar_grafo


def conversar() -> None:
    """Chat no terminal, numa thread só: o checkpointer lembra os turnos anteriores."""
    grafo = criar_grafo()
    config = {"configurable": {"thread_id": uuid.uuid4().hex}}
    print("Assistente Lean 4. Peça uma prova (ex.: Prove o teorema: (a b : Nat) : a + b = b + a). Ctrl+C sai.")
    while True:
        try:
            texto = input("\nvocê> ").strip()
        except (EOFError, KeyboardInterrupt):
            break
        if texto:
            estado = grafo.invoke({"messages": [HumanMessage(texto)]}, config)
            print(f"\nassistente> {estado['messages'][-1].content}")


class _SemModelo:
    """Substituto do modelo só para desenhar o grafo sem exigir a GROQ_API_KEY."""

    def bind_tools(self, ferramentas, **_):
        return self


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="python -m lean_agent",
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    comandos = parser.add_subparsers(dest="comando", required=True)
    casos = comandos.add_parser("casos", help="roda os 10 casos de teste da Unidade II")
    casos.add_argument("nomes", nargs="*", help="ex.: TESTE1_RAG TESTE7_GUARDRAIL_INJECTION (padrão: todos)")
    casos.add_argument("--pausa", type=float, default=2.0, help="segundos entre casos para evitar rate limit")
    comandos.add_parser("chat", help="conversa no terminal")
    comandos.add_parser("grafo", help="imprime o diagrama Mermaid do grafo")
    argumentos = parser.parse_args()

    for fluxo in (sys.stdout, sys.stderr):
        fluxo.reconfigure(encoding="utf-8", errors="replace")
    logging.basicConfig(level=logging.WARNING, format="   [%(name)s] %(message)s")

    if argumentos.comando == "casos":
        resultados = rodar_todos_casos(
            pausa=argumentos.pausa,
            nomes=argumentos.nomes or None,
            rastro=bool(argumentos.nomes),
        )
        print("\n" + tabela_markdown_unidade2(resultados))
    elif argumentos.comando == "chat":
        conversar()
    else:
        print(criar_grafo(llm=_SemModelo()).get_graph().draw_mermaid())


if __name__ == "__main__":
    main()
