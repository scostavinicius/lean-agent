"""O agente como grafo do LangGraph: estado, nós, arestas e guardrails.

    START → guardrail_entrada ─┬─ bloqueado ──────────────────────────────────────────────→ guardrail_saida → END
                               └─ aprovado → interpretar ─┬─ provar → planejar → agente ⇄ ferramentas
                                                          │                        │  ↑
                                                          │                        │  cobrar (nova rodada)
                                                          │                        ↓
                                                          │                     verificar ───────────┐
                                                          └─ conversa → conversar ⇄ ferramentas_conversa ┴→ guardrail_saida → END

A conversa com o usuário fica em `messages`, que o checkpointer guarda por thread.
O trabalho do turno atual (chamadas a RAG, Skills, MCP, táticas e erros do Lean) fica
em `rascunho`, que zera a cada pedido: assim a thread não carrega rascunhos antigos e
cada passo reenvia apenas o contexto necessário (a Groq limita tokens por minuto).
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

from .ferramentas import FERRAMENTAS, FERRAMENTAS_CONVERSA
from .guardrails import checar_guardrail_entrada, checar_guardrail_saida
from .lean import negar_enunciado, test_prova
from .modelo import criar_llm, gerar_estruturado
from .planejamento import criar_plano, formatar_plano
from .prompts import INTERPRETAR_SYSTEM, SYSTEM_AGENTE, SYSTEM_CONVERSA
from .skills import obter_catalogo_prompt

MAX_PASSOS = 6
MAX_RODADAS = 2
MAX_PASSOS_CONVERSA = 4
JANELA_CONVERSA = 8

PEDIDO_EXPLICITO = re.compile(r"^\s*(?:prove|demonstre)\s+o\s+teorema\s*:\s*(.+?)\s*$", re.IGNORECASE | re.DOTALL)


class Estado(TypedDict, total=False):
    messages: Annotated[list[AnyMessage], add_messages]
    rascunho: Annotated[list[AnyMessage], add_messages]
    intencao: Literal["provar", "conversa"]
    enunciado: str
    nome_arquivo: str
    plano: str
    tentativas: Annotated[list[dict], operator.add]
    negacao_aceita: str
    refutada: bool
    skills_carregadas: Annotated[list[str], operator.add]
    bloqueado_guardrail: bool
    motivo_bloqueio: str
    passos: int
    rodada: int
    aceita: bool
    prova: str


class Pedido(BaseModel):
    """O que o usuário quer com a última mensagem."""
    intencao: Literal["provar", "conversa"]
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
    max_passos_conversa: int = MAX_PASSOS_CONVERSA,
) -> CompiledStateGraph:
    """Monta e compila o grafo com Guardrails, RAG, MCP e Skills sob demanda."""
    llm = llm or criar_llm()
    llm_com_ferramentas = llm.bind_tools(FERRAMENTAS)
    llm_conversa = llm.bind_tools(FERRAMENTAS_CONVERSA)

    catalogo_skills = obter_catalogo_prompt()
    system_agente = f"{SYSTEM_AGENTE}\n\n{catalogo_skills}" if catalogo_skills else SYSTEM_AGENTE
    system_conversa = f"{SYSTEM_CONVERSA}\n\n{catalogo_skills}" if catalogo_skills else SYSTEM_CONVERSA

    # ---- nós --------------------------------------------------------------

    def guardrail_entrada(estado: Estado) -> dict:
        """Valida a última mensagem contra prompt injection, burla do Lean e desvio de escopo."""
        mensagens = estado.get("messages", [])
        ultima = mensagens[-1].content if mensagens else ""
        texto = ultima if isinstance(ultima, str) else str(ultima)

        aprovado, motivo = checar_guardrail_entrada(texto)
        if not aprovado:
            return {
                "bloqueado_guardrail": True,
                "motivo_bloqueio": motivo,
                "rascunho": [RemoveMessage(id=REMOVE_ALL_MESSAGES)],
                "skills_carregadas": Overwrite([]),
                "messages": [AIMessage(motivo)],
            }
        return {"bloqueado_guardrail": False, "motivo_bloqueio": ""}

    def interpretar(estado: Estado, config: RunnableConfig) -> dict:
        """Decide se a mensagem pede uma prova e prepara o estado do turno."""
        ultima = estado["messages"][-1].content
        explicito = PEDIDO_EXPLICITO.match(ultima) if isinstance(ultima, str) else None
        if explicito:
            pedido = Pedido(intencao="provar", enunciado=explicito.group(1).strip("` \n"))
        else:
            mensagens = [SystemMessage(INTERPRETAR_SYSTEM)] + estado["messages"][-JANELA_CONVERSA:]
            pedido = gerar_estruturado(llm, mensagens, Pedido)

        if pedido is None or pedido.intencao != "provar" or not pedido.enunciado.strip():
            return {
                "intencao": "conversa",
                "rascunho": [RemoveMessage(id=REMOVE_ALL_MESSAGES)],
                "skills_carregadas": Overwrite([]),
                "passos": 0,
                "aceita": False,
                "refutada": False,
            }

        return {
            "intencao": "provar",
            "enunciado": pedido.enunciado.strip(),
            "nome_arquivo": estado.get("nome_arquivo") or nome_do_arquivo(config),
            "plano": "",
            "tentativas": Overwrite([]),
            "negacao_aceita": "",
            "refutada": False,
            "skills_carregadas": Overwrite([]),
            "passos": 0,
            "rodada": 1,
            "aceita": False,
            "prova": "",
        }

    def planejar(estado: Estado) -> dict:
        """Pede o plano da prova e abre um rascunho novo com o pedido ao agente."""
        pedido = f"Prove o teorema: {estado['enunciado']}"
        plano = criar_plano(llm, estado["enunciado"])
        texto_plano = formatar_plano(plano) if plano else ""
        if texto_plano:
            pedido += "\n\n" + texto_plano
        return {
            "plano": texto_plano,
            "rascunho": [RemoveMessage(id=REMOVE_ALL_MESSAGES), HumanMessage(pedido)],
        }

    def agente(estado: Estado) -> dict:
        """Um passo do ReAct de prova: lê o rascunho e chama ferramentas ou responde em texto."""
        resposta = llm_com_ferramentas.invoke([SystemMessage(system_agente)] + estado["rascunho"])
        return {"rascunho": [resposta], "passos": estado["passos"] + 1}

    def cobrar(estado: Estado) -> dict:
        """Abre outra rodada quando o modelo parou sem o Lean aceitar nada."""
        tentativas = estado["tentativas"]
        ultimo = tentativas[-1]["resposta"] if tentativas else "nenhuma prova foi testada"
        return {
            "rodada": estado["rodada"] + 1,
            "passos": 0,
            "rascunho": [HumanMessage(
                "O Lean ainda não aceitou nenhuma prova, então a tarefa não terminou.\n"
                f"Último resultado de testar_tatica:\n{ultimo}\n"
                "Continue: carregue a skill `diagnostico_erros` se precisar, consulte a base "
                "com `consultar_documentacao`, tente `testar_negacao` se parecer falso ou proponha outra prova."
            )],
        }

    def verificar(estado: Estado) -> dict:
        """A palavra final é do Lean: verifica de novo fora do agente a prova ou refutação."""
        enunciado, tentativas = estado["enunciado"], estado["tentativas"]
        prova = primeira_aceita(tentativas)
        aceita = prova is not None and test_prova(enunciado, prova, estado["nome_arquivo"])[0]
        negacao = estado.get("negacao_aceita", "")
        refutada = (
            not aceita
            and bool(negacao)
            and test_prova(negar_enunciado(enunciado), negacao, f"{estado['nome_arquivo']}_negacao")[0]
        )
        explicacao = ultima_fala_do_agente(estado["rascunho"])

        if aceita:
            texto = f"Teorema `{enunciado}` provado e verificado pelo Lean:\n\n```lean\n{prova}\n```"
        elif refutada:
            texto = (
                f"Teorema `{enunciado}` REFUTADO (falso) e verificado pelo Lean:\n\n"
                f"```lean\n{negacao}\n```"
            )
            prova = negacao
        else:
            ultimo_erro = tentativas[-1]["erro"] if tentativas else "nenhuma prova foi testada"
            texto = (
                f"Não consegui uma prova de `{enunciado}` que o Lean aceitasse "
                f"({len(tentativas)} prova(s) testada(s) em {estado['rodada']} rodada(s)).\n\n"
                f"Último erro do Lean: {ultimo_erro}"
            )
        if explicacao:
            texto += "\n\n" + explicacao
        return {"aceita": aceita, "refutada": refutada, "prova": prova or "", "messages": [AIMessage(texto)]}

    def conversar(estado: Estado) -> dict:
        """Responde dúvidas e consultas com RAG, Skills e MCP usando o histórico da thread."""
        historico = estado["messages"][-JANELA_CONVERSA:]
        msgs_loop = [SystemMessage(system_conversa)] + historico + estado.get("rascunho", [])
        if estado.get("passos", 0) >= max_passos_conversa:
            resposta = llm.invoke(msgs_loop)
            return {"messages": [resposta]}

        resposta = llm_conversa.invoke(msgs_loop)
        if getattr(resposta, "tool_calls", None):
            return {"rascunho": [resposta], "passos": estado.get("passos", 0) + 1}
        return {"messages": [resposta]}

    def guardrail_saida(estado: Estado) -> dict:
        """Audita a resposta final contra vazamento de chaves/prompts e alucinação de veredito."""
        mensagens = estado.get("messages", [])
        if not mensagens:
            return {}
        ultima = mensagens[-1]
        if isinstance(ultima, AIMessage) and isinstance(ultima.content, str):
            _, texto_sanitizado = checar_guardrail_saida(
                ultima.content,
                aceita=estado.get("aceita", False),
                refutada=estado.get("refutada", False),
                intencao=estado.get("intencao", ""),
            )
            if texto_sanitizado != ultima.content:
                msg_id = getattr(ultima, "id", None)
                if msg_id:
                    return {"messages": [AIMessage(content=texto_sanitizado, id=msg_id)]}
                return {"messages": [AIMessage(content=texto_sanitizado)]}
        return {}

    # ---- arestas condicionais ---------------------------------------------

    def rotear_guardrail_entrada(estado: Estado) -> Literal["guardrail_saida", "interpretar"]:
        return "guardrail_saida" if estado.get("bloqueado_guardrail") else "interpretar"

    def rotear_intencao(estado: Estado) -> Literal["planejar", "conversar"]:
        return "planejar" if estado["intencao"] == "provar" else "conversar"

    def fim_da_rodada(estado: Estado) -> Literal["cobrar", "verificar"]:
        if (
            primeira_aceita(estado["tentativas"]) is not None
            or estado.get("negacao_aceita")
            or estado["rodada"] >= max_rodadas
        ):
            return "verificar"
        return "cobrar"

    def depois_do_agente(estado: Estado) -> Literal["ferramentas", "cobrar", "verificar"]:
        if estado["rascunho"][-1].tool_calls:
            return "ferramentas"
        return fim_da_rodada(estado)

    def depois_das_ferramentas(estado: Estado) -> Literal["agente", "cobrar", "verificar"]:
        if estado["passos"] < max_passos:
            return "agente"
        return fim_da_rodada(estado)

    def depois_de_conversar(estado: Estado) -> Literal["ferramentas_conversa", "guardrail_saida"]:
        if (
            estado.get("messages")
            and isinstance(estado["messages"][-1], HumanMessage)
            and estado.get("rascunho")
            and getattr(estado["rascunho"][-1], "tool_calls", None)
        ):
            return "ferramentas_conversa"
        return "guardrail_saida"

    # ---- montagem ---------------------------------------------------------

    grafo = StateGraph(Estado)
    grafo.add_node("guardrail_entrada", guardrail_entrada)
    grafo.add_node("interpretar", interpretar)
    grafo.add_node("planejar", planejar)
    grafo.add_node("agente", agente)
    grafo.add_node("ferramentas", ToolNode(FERRAMENTAS, messages_key="rascunho"))
    grafo.add_node("cobrar", cobrar)
    grafo.add_node("verificar", verificar)
    grafo.add_node("conversar", conversar)
    grafo.add_node("ferramentas_conversa", ToolNode(FERRAMENTAS_CONVERSA, messages_key="rascunho"))
    grafo.add_node("guardrail_saida", guardrail_saida)

    grafo.add_edge(START, "guardrail_entrada")
    grafo.add_conditional_edges("guardrail_entrada", rotear_guardrail_entrada)
    grafo.add_conditional_edges("interpretar", rotear_intencao)
    grafo.add_edge("planejar", "agente")
    grafo.add_conditional_edges("agente", depois_do_agente)
    grafo.add_conditional_edges("ferramentas", depois_das_ferramentas)
    grafo.add_edge("cobrar", "agente")
    grafo.add_conditional_edges("conversar", depois_de_conversar)
    grafo.add_edge("ferramentas_conversa", "conversar")
    grafo.add_edge("verificar", "guardrail_saida")
    grafo.add_edge("guardrail_saida", END)

    limite = 4 + max(max_rodadas * (2 * max_passos + 1), 2 * max_passos_conversa + 2)
    compilado = grafo.compile(checkpointer=checkpointer or InMemorySaver())
    return compilado.with_config(recursion_limit=limite + 5)


def provar(grafo: CompiledStateGraph, enunciado: str, nome_arquivo: str = "Prova") -> Estado:
    """Pede a prova de um teorema numa thread nova e devolve o estado final."""
    config = {"configurable": {"thread_id": f"{nome_arquivo}-{uuid.uuid4().hex[:8]}"}}
    entrada = {"messages": [HumanMessage(f"Prove o teorema: {enunciado}")], "nome_arquivo": nome_arquivo}
    return grafo.invoke(entrada, config)
