"""Os teoremas que o agente precisa provar e o que se espera de cada um.

"provar" quer dizer que o teorema é verdadeiro. "falso" marca uma armadilha: o
teorema não vale em Nat, e o agente acerta se NÃO aceitar prova nenhuma.
"""

CASOS = [
    {"nome": "TESTE1",  "enunciado": "(a b : Nat) : a + b = b + a",            "esperado": "provar"},
    {"nome": "TESTE2",  "enunciado": "(p q : Prop) (hp : p) (hq : q) : p ∧ q", "esperado": "provar"},
    {"nome": "TESTE3",  "enunciado": "(p q : Prop) : p ∧ q → q ∧ p",           "esperado": "provar"},
    {"nome": "TESTE4",  "enunciado": "∃ n : Nat, n * n = 49",                  "esperado": "provar"},
    {"nome": "TESTE5",  "enunciado": "(p q : Prop) : (p → q) → ¬q → ¬p",       "esperado": "provar"},
    {"nome": "TESTE6",  "enunciado": "(a b : Nat) : a - b + b = a",            "esperado": "falso"},  # a=0, b=1: 0 - 1 + 1 = 1
    {"nome": "TESTE7",  "enunciado": "(n : Nat) : dobro n = 2 * n",            "esperado": "provar"},
    {"nome": "TESTE8",  "enunciado": "(n : Nat) : 2 * soma n = n * (n + 1)",   "esperado": "provar"},
    {"nome": "TESTE9",  "enunciado": "(xs : List Nat) : rev (rev xs) = xs",    "esperado": "provar"},
    {"nome": "TESTE10", "enunciado": "∀ n : Nat, n ^ 2 ≥ 2 * n",               "esperado": "falso"},  # n=1: 1 ≥ 2
]

# Antes de medir o agente, provar que a régua funciona. Cada caso verdadeiro tem
# uma prova escrita à mão; se o Lean recusar alguma, o defeito está no harness
# (cabeçalho, definições), não no modelo.
PROVAS_REFERENCIA = {
    "TESTE1": "omega",
    "TESTE2": "exact ⟨hp, hq⟩",
    "TESTE3": "intro h\nexact ⟨h.2, h.1⟩",
    "TESTE4": "exact ⟨7, rfl⟩",
    "TESTE5": "intro hpq hnq hp\nexact hnq (hpq hp)",
    "TESTE7": """induction n with
| zero => rfl
| succ n ih =>
  simp only [dobro]
  omega""",
    "TESTE8": """induction n with
| zero => rfl
| succ n ih =>
  simp only [soma, Nat.mul_add, Nat.add_mul, Nat.mul_one, Nat.one_mul] at *
  omega""",
    "TESTE9": """have aux : ∀ (ys : List Nat) (x : Nat), rev (ys ++ [x]) = x :: rev ys := by
  intro ys x
  induction ys with
  | nil => simp [rev]
  | cons y ys ih => simp [rev, ih]
induction xs with
| nil => rfl
| cons x xs ih => simp [rev, aux, ih]""",
}

# Nos casos falsos, o Lean precisa aceitar a negação, provada com o contraexemplo:
# é a garantia de que não existe prova.
REFUTACOES = {
    "TESTE6": ("¬ ∀ a b : Nat, a - b + b = a", "intro h\nexact absurd (h 0 1) (by decide)"),
    "TESTE10": ("¬ ∀ n : Nat, n ^ 2 ≥ 2 * n", "intro h\nexact absurd (h 1) (by decide)"),
}
