# Por quê: testar as arestas do grafo sem gastar a API. Um modelo roteirizado
# devolve respostas fixas, e o Lean é o de verdade: o que se verifica aqui é o
# caminho que o estado percorre (rodadas, limite de passos, memória da thread).
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from lean_agent.ferramentas import testar_tatica
from lean_agent.grafo import Pedido, criar_grafo, provar
from lean_agent.planejamento import Passo, Plano

from .conftest import requer_lean

PLANO = Plano(passos=[Passo(instrucao="usar aritmética linear", tatica_provavel="omega", resultado_esperado="fim")] * 2)


class ModeloRoteirizado:
    """Imita o ChatGroq: cada invoke devolve a próxima resposta do roteiro."""

    def __init__(self, respostas: list, estruturadas: list | None = None):
        self.respostas = list(respostas)
        self.estruturadas = list(estruturadas or [])

    def bind_tools(self, ferramentas, **_):
        return self

    def with_structured_output(self, esquema, **_):
        modelo = self

        class _Estruturado:
            def invoke(self, mensagens):
                resposta = modelo.estruturadas.pop(0)
                if isinstance(resposta, Exception):
                    raise resposta
                return resposta

        return _Estruturado()

    def invoke(self, mensagens, **_):
        return self.respostas.pop(0)


def chamada(prova: str, id_: str) -> AIMessage:
    return AIMessage("", tool_calls=[{"name": "testar_tatica", "args": {"prova": prova}, "id": id_, "type": "tool_call"}])


def test_modelo_nao_escolhe_o_enunciado():
    # Só `prova` chega ao modelo; enunciado e arquivo vêm do estado.
    assert set(testar_tatica.tool_call_schema.model_json_schema()["properties"]) == {"prova"}


@requer_lean
def test_prova_aceita_depois_de_um_erro():
    modelo = ModeloRoteirizado(
        respostas=[chamada("rfl", "c1"), chamada("omega", "c2"), AIMessage("omega fecha aritmética linear.")],
        estruturadas=[PLANO],
    )
    estado = provar(criar_grafo(modelo), "(a b : Nat) : a + b = b + a", "Comutativa")

    assert estado["aceita"] and estado["prova"] == "omega"
    assert [t["aceita"] for t in estado["tentativas"]] == [False, True]
    assert "RECUSADA" in estado["rascunho"][2].content  # o erro do rfl voltou ao modelo
    assert "omega" in estado["messages"][-1].content and estado["rodada"] == 1
    assert "PLANO DA PROVA" in estado["plano"]
    assert not modelo.respostas


@requer_lean
def test_modelo_desiste_e_o_grafo_cobra_outra_rodada():
    # Saída estruturada recusada e JSON inválido: segue sem plano.
    modelo = ModeloRoteirizado(
        respostas=[AIMessage("sem json"), AIMessage("Desisto."), AIMessage("Desisto de novo.")],
        estruturadas=[RuntimeError("json_schema não suportado")],
    )
    estado = provar(criar_grafo(modelo, max_rodadas=2), "(a b : Nat) : a - b + b = a", "Falso")

    assert not estado["aceita"] and estado["rodada"] == 2 and estado["plano"] == ""
    cobrancas = [m for m in estado["rascunho"][1:] if isinstance(m, HumanMessage)]
    assert len(cobrancas) == 1 and "ainda não aceitou" in cobrancas[0].content
    assert "Não consegui" in estado["messages"][-1].content


@requer_lean
def test_limite_de_passos_encerra_a_rodada_sem_chamada_pendente():
    modelo = ModeloRoteirizado(respostas=[chamada("rfl", "c1")], estruturadas=[PLANO])
    estado = provar(criar_grafo(modelo, max_passos=1, max_rodadas=1), "(a b : Nat) : a + b = b + a")

    assert not estado["aceita"] and estado["passos"] == 1
    # A chamada do último passo foi executada: toda chamada tem a sua resposta.
    assert isinstance(estado["rascunho"][-1], ToolMessage)


@requer_lean
def test_segundo_teorema_na_mesma_thread_comeca_do_zero():
    modelo = ModeloRoteirizado(
        respostas=[chamada("rfl", "c1"), chamada("omega", "c2"), AIMessage("Feito."),
                   chamada("exact ⟨hp, hq⟩", "c3"), AIMessage("Feito.")],
        estruturadas=[PLANO, PLANO],
    )
    grafo = criar_grafo(modelo)
    config = {"configurable": {"thread_id": "duas-provas"}}
    grafo.invoke({"messages": [HumanMessage("Prove o teorema: (a b : Nat) : a + b = b + a")]}, config)
    estado = grafo.invoke({"messages": [HumanMessage("Prove o teorema: (p q : Prop) (hp : p) (hq : q) : p ∧ q")]},
                          config)

    # O teorema anterior não vaza para o novo: tentativas e rascunho zeraram...
    assert [t["prova"] for t in estado["tentativas"]] == ["exact ⟨hp, hq⟩"]
    assert "p ∧ q" in estado["rascunho"][0].content and len(estado["rascunho"]) == 4
    # ...mas a conversa guarda os dois pedidos e as duas respostas.
    assert len(estado["messages"]) == 4 and estado["aceita"]
    assert estado["nome_arquivo"].startswith("Prova_")


def test_conversa_usa_a_memoria_da_thread():
    modelo = ModeloRoteirizado(
        respostas=[AIMessage("omega resolve aritmética linear em Nat e Int."), AIMessage("Falávamos de omega.")],
        estruturadas=[Pedido(intencao="conversa", enunciado=""), Pedido(intencao="conversa", enunciado="")],
    )
    grafo = criar_grafo(modelo)
    config = {"configurable": {"thread_id": "t1"}}
    grafo.invoke({"messages": [HumanMessage("O que faz a tática omega?")]}, config)
    estado = grafo.invoke({"messages": [HumanMessage("Do que falávamos?")]}, config)

    assert [m.content for m in estado["messages"]] == [
        "O que faz a tática omega?", "omega resolve aritmética linear em Nat e Int.",
        "Do que falávamos?", "Falávamos de omega.",
    ]
    # Outra thread começa vazia.
    outra = grafo.get_state({"configurable": {"thread_id": "t2"}})
    assert not outra.values
