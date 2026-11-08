# Por quê: cada log abaixo imita um formato que o Lean produz de verdade, com o
# que o parser precisa extrair dele. Os três primeiros casos quebravam a versão
# antiga, que usava uma regex só para o log inteiro.
import pytest

from lean_agent.parser import parsear

TESTES_PARSER = [
    ("hipótese com símbolos (∧)",
     "Prova.lean:15:2: error: unsolved goals\np q : Prop\nh : p ∧ q\n⊢ q ∧ p\n",
     {"tipo": "erro_compilacao", "mensagem_limpa": "unsolved goals",
      "hipoteses": "p q : Prop\nh : p ∧ q", "objetivo": "q ∧ p"}),
    ("dois erros: só o primeiro entra",
     "Prova.lean:15:12: error: unsolved goals\ncase zero\n⊢ dobro 0 = 2 * 0\n"
     "Prova.lean:16:4: error: unsolved goals\ncase succ\nn : Nat\nih : dobro n = 2 * n\n⊢ dobro (n + 1) = 2 * (n + 1)\n",
     {"mensagem_limpa": "unsolved goals\n(e mais 1 erro(s) depois deste)",
      "hipoteses": "case zero", "objetivo": "dobro 0 = 2 * 0"}),
    ("erro e sorry juntos: o erro vence",
     "Prova.lean:14:8: warning: declaration uses `sorry`\nProva.lean:15:2: error: unknown identifier 'foo'\n",
     {"tipo": "erro_compilacao", "mensagem_limpa": "unknown identifier 'foo'", "hipoteses": "", "objetivo": ""}),
    ("rfl falhou: explicação, linha em branco e contexto",
     "Prova.lean:14:2: error: Tactic `rfl` failed: The left-hand side\n  a + b\n"
     "is not definitionally equal to the right-hand side\n  b + a\n\na b : Nat\n⊢ a + b = b + a\n",
     {"tipo": "erro_compilacao", "hipoteses": "a b : Nat", "objetivo": "a + b = b + a"}),
    ("objetivo quebrado em duas linhas",
     "Prova.lean:17:4: error: unsolved goals\ncase succ\nn : Nat\nih : 2 * soma n = n * (n + 1)\n"
     "⊢ 2 * (soma n + (n + 1)) =\n    (n + 1) * (n + 1 + 1)\n",
     {"hipoteses": "case succ\nn : Nat\nih : 2 * soma n = n * (n + 1)",
      "objetivo": "2 * (soma n + (n + 1)) =\n(n + 1) * (n + 1 + 1)"}),
    ("erro sem estado da prova",
     "Teste1.lean:8:6: error: No goals to be solved\n",
     {"tipo": "erro_compilacao", "mensagem_limpa": "No goals to be solved", "hipoteses": "", "objetivo": ""}),
    ("só sorry",
     "Prova.lean:14:8: warning: declaration uses `sorry`\n",
     {"tipo": "sorry_pendente"}),
    ("timeout do test_prova",
     "Prova.lean: error: o Lean passou de 60 s e foi interrompido",
     {"tipo": "erro_compilacao", "mensagem_limpa": "o Lean passou de 60 s e foi interrompido"}),
]


@pytest.mark.parametrize("log, esperado", [t[1:] for t in TESTES_PARSER], ids=[t[0] for t in TESTES_PARSER])
def test_parsear(log, esperado):
    obtido = parsear(log)
    assert {chave: obtido.get(chave) for chave in esperado} == esperado
