"""Roda os casos de teste pelo grafo e mostra o rastro e o custo de cada um."""
import time

from langchain_core.callbacks import get_usage_metadata_callback
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langgraph.graph.state import CompiledStateGraph

from .casos import CASOS
from .grafo import criar_grafo, provar

# Plano gratuito da Groq para o gpt-oss-120b. Sem medir, "o agente gasta muito" é
# palpite (aula 07, Custo).
LIMITE_DIARIO_TOKENS = 200_000


def resumo_uso(uso: dict) -> str:
    """Resume o que o get_usage_metadata_callback juntou, somando todos os modelos."""
    entrada = sum(u.get("input_tokens", 0) for u in uso.values())
    saida = sum(u.get("output_tokens", 0) for u in uso.values())
    return (f"{entrada} tokens de entrada e {saida} de saída "
            f"({(entrada + saida) / LIMITE_DIARIO_TOKENS:.1%} do limite diário)")


def mostrar_rastro(estado: dict) -> None:
    """Imprime cada ferramenta que o agente escolheu, com que argumentos, e o que recebeu de volta.

    É a evidência de que a decisão é dele.
    """
    if estado.get("plano"):
        print(estado["plano"])
    passo = 0
    for mensagem in estado.get("rascunho", [])[1:]:
        if isinstance(mensagem, HumanMessage):
            # Depois do pedido inicial, mensagem de usuário é o nó cobrar abrindo outra rodada.
            print("\n[cobrar] o Lean ainda não aceitou nenhuma prova: nova rodada")
        elif isinstance(mensagem, AIMessage) and mensagem.tool_calls:
            for chamada in mensagem.tool_calls:
                passo += 1
                argumentos = ", ".join(f"{k}={v!r}" for k, v in chamada["args"].items())
                print(f"\npasso {passo}: {chamada['name']}({argumentos[:160]})")
        elif isinstance(mensagem, ToolMessage):
            print(f"   -> {str(mensagem.content).strip().splitlines()[0][:160]}")
        elif isinstance(mensagem, AIMessage) and mensagem.content:
            print(f"\nresposta do agente ({passo} ferramenta(s) usada(s) até aqui):\n{mensagem.content}")


def rodar_casos(nomes: list[str] | None = None, pausa: float = 0.0, rastro: bool = False,
                grafo: CompiledStateGraph | None = None) -> list[dict]:
    """Roda os casos pelo grafo e imprime a tabela de resultados, com quanto cada caso custou."""
    grafo = grafo or criar_grafo()
    escolhidos = [c for c in CASOS if not nomes or c["nome"] in nomes]
    resultados = []
    with get_usage_metadata_callback() as total:
        for caso in escolhidos:
            print("=" * 72)
            print(f"{caso['nome']}: {caso['enunciado']}")
            # Só a execução do grafo fica no try: um erro ao imprimir o rastro é
            # defeito do harness e não pode aparecer na tabela como falha do agente.
            with get_usage_metadata_callback() as uso:
                try:
                    estado = provar(grafo, caso["enunciado"], caso["nome"])
                except Exception as falha:
                    estado = None
                    aceita, prova, erro = False, "", f"{type(falha).__name__}: {falha}"
            if estado is not None:
                aceita, prova = estado["aceita"], estado["prova"]
                erro = estado["tentativas"][-1]["erro"] if estado["tentativas"] else "nenhuma prova foi testada"
                if rastro:
                    mostrar_rastro(estado)
                print(f"   -> {'aceita' if aceita else 'não aceita'} em {estado['rodada']} rodada(s), "
                      f"{len(estado['tentativas'])} prova(s) testada(s)")
            # O caso está certo quando o resultado bate com o esperado: nos falsos, acertar é NÃO provar.
            acertou = aceita == (caso["esperado"] == "provar")
            tokens = sum(u.get("total_tokens", 0) for u in uso.usage_metadata.values())
            resultados.append({**caso, "aceita": aceita, "acertou": acertou, "tokens": tokens,
                               "detalhe": prova if aceita else erro})
            time.sleep(pausa)

    print("\n" + "=" * 72)
    print(f"{'caso':8} {'esperado':9} {'aceita':7} {'acertou':8} {'tokens':>7}  prova / último erro")
    for r in resultados:
        print(f"{r['nome']:8} {r['esperado']:9} {'sim' if r['aceita'] else 'nao':7} "
              f"{'sim' if r['acertou'] else 'NAO':8} {r['tokens']:>7}  "
              f"{r['detalhe'][:60].replace(chr(10), ' / ')}")
    print(f"\n{sum(r['acertou'] for r in resultados)}/{len(resultados)} casos com o resultado esperado")
    print(resumo_uso(total.usage_metadata))
    return resultados


def _celula(texto: str, limite: int = 120) -> str:
    """Texto que cabe numa célula de tabela Markdown: uma linha só, sem quebrar a coluna no `|`."""
    texto = " / ".join(linha.strip() for linha in texto.strip().splitlines() if linha.strip())
    if len(texto) > limite:
        texto = texto[:limite] + "…"
    return texto.replace("|", "\\|")


def tabela_markdown(resultados: list[dict]) -> str:
    """A tabela no formato que o README pede: entrada, resultado esperado, obtido e se foi aprovado."""
    linhas = ["| caso | entrada | resultado esperado | resultado obtido | aprovado | tokens |",
              "|---|---|---|---|---|---|"]
    for r in resultados:
        esperado = "prova aceita pelo Lean" if r["esperado"] == "provar" else "nenhuma prova aceita (teorema falso)"
        obtido = (f"prova aceita: `{_celula(r['detalhe'])}`" if r["aceita"]
                  else f"nenhuma prova aceita; último erro: {_celula(r['detalhe'])}")
        linhas.append(f"| {r['nome']} | `{_celula(r['enunciado'])}` | {esperado} | {obtido} | "
                      f"{'sim' if r['acertou'] else 'não'} | {r['tokens']} |")
    acertos = sum(r["acertou"] for r in resultados)
    taxa = acertos / len(resultados) if resultados else 0
    return "\n".join(linhas) + f"\n\n**Taxa de acerto:** {acertos}/{len(resultados)} ({taxa:.0%})"
