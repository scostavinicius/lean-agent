"""O agente como grafo do LangGraph: estado, nós e arestas.

    START → interpretar ─┬─ provar ───→ planejar → agente ⇄ ferramentas
                         │                           │  ↑
                         │                           │  cobrar (nova rodada, se o Lean não aceitou)
                         │                           ↓
                         │                        verificar → END
                         └─ conversa ──→ conversar → END

A conversa com o usuário fica em `messages`, que o checkpointer guarda por thread.
O trabalho de cada teorema (pedido, chamadas de ferramenta, erros do Lean) fica
em `rascunho`, que zera a cada teorema: assim a thread não carrega o histórico de
tentativas antigas e cada passo do agente reenvia só o teorema atual.
"""
import operator
import re
import uuid
from typing import Annotated, Literal, TypedDict

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, AnyMessage, HumanMessage, RemoveMessage, SystemMessage
from langchain_core.runnables import RunnableConfig
from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import END, START, StateGraph
from langgraph.graph.message import REMOVE_ALL_MESSAGES, add_messages
from langgraph.graph.state import CompiledStateGraph
from langgraph.prebuilt import ToolNode
from langgraph.types import Overwrite
from pydantic import BaseModel, Field

from .ferramentas import FERRAMENTAS
from .lean import test_prova
from .modelo import criar_llm, gerar_estruturado
from .planejamento import criar_plano, formatar_plano
from .prompts import INTERPRETAR_SYSTEM, SYSTEM_AGENTE, SYSTEM_CONVERSA

# Cada passo reenvia o rascunho inteiro, então o limite de passos também é um
# limite de gasto: 6 chamadas ao agente por rodada, e o grafo decide se há outra rodada.
MAX_PASSOS = 6
MAX_RODADAS = 2

# Só as últimas mensagens da thread vão para interpretar e conversar: a Groq
# limita tokens por minuto, e a thread cresce a cada turno.
JANELA_CONVERSA = 8

# "Prove o teorema: <enunciado>" já traz o enunciado em Lean: ele é copiado sem
# passar pelo modelo, que poderia reescrevê-lo.
PEDIDO_EXPLICITO = re.compile(r"^\s*(?:prove|demonstre)\s+o\s+teorema\s*:\s*(.+?)\s*$", re.IGNORECASE | re.DOTALL)


class Estado(TypedDict, total=False):
    # A conversa com o usuário: pedidos e respostas finais, guardados pelo checkpointer.
    messages: Annotated[list[AnyMessage], add_messages]
    # O ReAct do teorema atual: pedido com o plano, chamadas de ferramenta e respostas.
    rascunho: Annotated[list[AnyMessage], add_messages]
    intencao: Literal["provar", "conversa"]
    enunciado: str
    nome_arquivo: str
    plano: str
    tentativas: Annotated[list[dict], operator.add]  # uma entrada por chamada a testar_tatica
    passos: int      # chamadas ao agente na rodada atual
    rodada: int
    aceita: bool     # veredito do Lean, conferido de novo no nó verificar
    prova: str


class Pedido(BaseModel):
    """O que o usuário quer com a última mensagem."""
    intencao: Literal["provar", "conversa"]
    # Sem valor padrão de propósito: com "default" no schema, o modo strict da Groq
    # devolveu geração vazia em 5 de 8 conversas; sem ele, 8 de 8 passaram.
    enunciado: str = Field(description='Enunciado Lean 4 sem "theorem" e sem ":= by"; vazio se for conversa.')


def primeira_aceita(tentativas: list[dict]) -> str | None:
    """A primeira prova que o Lean aceitou, ou None."""
    return next((t["prova"] for t in tentativas if t["aceita"]), None)


def ultima_fala_do_agente(rascunho: list[AnyMessage]) -> str:
    """O último texto do agente na rodada atual (depois do último pedido do harness)."""
    for mensagem in reversed(rascunho):
        if isinstance(mensagem, HumanMessage):
            break
        if isinstance(mensagem, AIMessage) and not mensagem.tool_calls and isinstance(mensagem.content, str):
            if mensagem.content.strip():
                return mensagem.content.strip()
    return ""


def nome_do_arquivo(config: RunnableConfig) -> str:
    """Um .lean por thread, para duas conversas abertas não sobrescreverem o arquivo uma da outra."""
    thread = str(config.get("configurable", {}).get("thread_id", ""))
    return "Prova_" + re.sub(r"[^A-Za-z0-9_]", "", thread)[:16] if thread else "Prova"


def criar_grafo(
    llm: BaseChatModel | None = None,
    checkpointer: BaseCheckpointSaver | None = None,
    max_passos: int = MAX_PASSOS,
    max_rodadas: int = MAX_RODADAS,
) -> CompiledStateGraph:
    """Monta e compila o grafo. Sem checkpointer, usa um em memória (uma thread por conversa)."""
    llm = llm or criar_llm()
    # bind_tools devolve uma CÓPIA do modelo: o `llm` continua sem ferramentas, e por
    # isso interpretar, planejar e conversar seguem recebendo texto.
    llm_com_ferramentas = llm.bind_tools(FERRAMENTAS)

    # ---- nós --------------------------------------------------------------

    def interpretar(estado: Estado, config: RunnableConfig) -> dict:
        """Decide se a mensagem pede uma prova e fixa o enunciado no estado."""
        ultima = estado["messages"][-1].content
        explicito = PEDIDO_EXPLICITO.match(ultima) if isinstance(ultima, str) else None
        if explicito:
            pedido = Pedido(intencao="provar", enunciado=explicito.group(1).strip("` \n"))
        else:
            mensagens = [SystemMessage(INTERPRETAR_SYSTEM)] + estado["messages"][-JANELA_CONVERSA:]
            pedido = gerar_estruturado(llm, mensagens, Pedido)

        if pedido is None or pedido.intencao != "provar" or not pedido.enunciado.strip():
            return {"intencao": "conversa"}
        # Teorema novo: tudo o que era do teorema anterior volta ao zero.
        return {
            "intencao": "provar", "enunciado": pedido.enunciado.strip(),
            "nome_arquivo": estado.get("nome_arquivo") or nome_do_arquivo(config),
            "plano": "", "tentativas": Overwrite([]), "passos": 0, "rodada": 1, "aceita": False, "prova": "",
        }

    def planejar(estado: Estado) -> dict:
        """Pede o plano da prova e abre um rascunho novo com o pedido ao agente."""
        pedido = f"Prove o teorema: {estado['enunciado']}"
        plano = criar_plano(llm, estado["enunciado"])
        texto_plano = formatar_plano(plano) if plano else ""
        if texto_plano:
            pedido += "\n\n" + texto_plano
        return {"plano": texto_plano, "rascunho": [RemoveMessage(id=REMOVE_ALL_MESSAGES), HumanMessage(pedido)]}

    def agente(estado: Estado) -> dict:
        """Um passo do ReAct: o modelo lê o rascunho e chama uma ferramenta ou responde em texto."""
        resposta = llm_com_ferramentas.invoke([SystemMessage(SYSTEM_AGENTE)] + estado["rascunho"])
        return {"rascunho": [resposta], "passos": estado["passos"] + 1}

    def cobrar(estado: Estado) -> dict:
        """Abre outra rodada: devolve ao modelo o último resultado do Lean e pede para continuar."""
        tentativas = estado["tentativas"]
        ultimo = tentativas[-1]["resposta"] if tentativas else "nenhuma prova foi testada"
        return {"rodada": estado["rodada"] + 1, "passos": 0, "rascunho": [HumanMessage(
            "O Lean ainda não aceitou nenhuma prova, então a tarefa não terminou.\n"
            f"Último resultado de testar_tatica:\n{ultimo}\n"
            "Continue: proponha outra prova e teste com testar_tatica."
        )]}

    def verificar(estado: Estado) -> dict:
        """A palavra final é do Lean: a prova registrada é verificada de novo, fora do agente."""
        enunciado, tentativas = estado["enunciado"], estado["tentativas"]
        prova = primeira_aceita(tentativas)
        aceita = prova is not None and test_prova(enunciado, prova, estado["nome_arquivo"])[0]
        explicacao = ultima_fala_do_agente(estado["rascunho"])

        if aceita:
            texto = f"Teorema `{enunciado}` provado e verificado pelo Lean:\n\n```lean\n{prova}\n```"
        else:
            ultimo_erro = tentativas[-1]["erro"] if tentativas else "nenhuma prova foi testada"
            texto = (f"Não consegui uma prova de `{enunciado}` que o Lean aceitasse "
                     f"({len(tentativas)} prova(s) testada(s) em {estado['rodada']} rodada(s)).\n\n"
                     f"Último erro do Lean: {ultimo_erro}")
        if explicacao:
            texto += "\n\n" + explicacao
        return {"aceita": aceita, "prova": prova or "", "messages": [AIMessage(texto)]}

    def conversar(estado: Estado) -> dict:
        """Responde o que não é pedido de prova, com as últimas mensagens da thread."""
        resposta = llm.invoke([SystemMessage(SYSTEM_CONVERSA)] + estado["messages"][-JANELA_CONVERSA:])
        return {"messages": [resposta]}

    # ---- arestas condicionais ---------------------------------------------

    def rotear_intencao(estado: Estado) -> Literal["planejar", "conversar"]:
        return "planejar" if estado["intencao"] == "provar" else "conversar"

    def fim_da_rodada(estado: Estado) -> Literal["cobrar", "verificar"]:
        # Quem decide que acabou é o Lean, não o modelo dizendo que terminou (aula 07).
        if primeira_aceita(estado["tentativas"]) is not None or estado["rodada"] >= max_rodadas:
            return "verificar"
        return "cobrar"

    def depois_do_agente(estado: Estado) -> Literal["ferramentas", "cobrar", "verificar"]:
        # Toda chamada de ferramenta é executada, mesmo no último passo: uma chamada
        # sem resposta no rascunho faz a API recusar o pedido seguinte.
        if estado["rascunho"][-1].tool_calls:
            return "ferramentas"
        return fim_da_rodada(estado)

    def depois_das_ferramentas(estado: Estado) -> Literal["agente", "cobrar", "verificar"]:
        if estado["passos"] < max_passos:
            return "agente"
        return fim_da_rodada(estado)

    # ---- montagem ---------------------------------------------------------

    grafo = StateGraph(Estado)
    grafo.add_node("interpretar", interpretar)
    grafo.add_node("planejar", planejar)
    grafo.add_node("agente", agente)
    grafo.add_node("ferramentas", ToolNode(FERRAMENTAS, messages_key="rascunho"))
    grafo.add_node("cobrar", cobrar)
    grafo.add_node("verificar", verificar)
    grafo.add_node("conversar", conversar)

    grafo.add_edge(START, "interpretar")
    grafo.add_conditional_edges("interpretar", rotear_intencao)
    grafo.add_edge("planejar", "agente")
    grafo.add_conditional_edges("agente", depois_do_agente)
    grafo.add_conditional_edges("ferramentas", depois_das_ferramentas)
    grafo.add_edge("cobrar", "agente")
    grafo.add_edge("verificar", END)
    grafo.add_edge("conversar", END)

    # Pior caso de um teorema: interpretar, planejar, as rodadas cheias (agente +
    # ferramentas a cada passo, mais o cobrar) e verificar. O padrão do LangGraph (25) não basta.
    limite = 3 + max_rodadas * (2 * max_passos + 1)
    compilado = grafo.compile(checkpointer=checkpointer or InMemorySaver())
    return compilado.with_config(recursion_limit=limite + 5)


def provar(grafo: CompiledStateGraph, enunciado: str, nome_arquivo: str = "Prova") -> Estado:
    """Pede a prova de um teorema numa thread nova e devolve o estado final (usado pelos casos de teste)."""
    config = {"configurable": {"thread_id": f"{nome_arquivo}-{uuid.uuid4().hex[:8]}"}}
    entrada = {"messages": [HumanMessage(f"Prove o teorema: {enunciado}")], "nome_arquivo": nome_arquivo}
    return grafo.invoke(entrada, config)
