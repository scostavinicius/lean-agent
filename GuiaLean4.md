"intro": """
    Tática `intro`:
    Usada para introduzir variáveis ou hipóteses no contexto local a partir de implicações (→) ou quantificadores universais (∀).
    Exemplo:
      theorem exemplo (p q : Prop) : p → q → p := by
        intro hp hq
        exact hp
    """,
        "rw": """
    Tática `rw` (rewrite):
    Substitui termos usando igualdades provadas ou hipóteses. Use colchetes.
    Para reescrever no sentido inverso, use a seta para a esquerda: `rw [← lema]`.
    Exemplo:
      rw [Nat.add_zero]
      rw [Nat.add_succ, ih]
    """,
        "induction": """
    Tática `induction`:
    Usada para prova por indução matemática sobre tipos indutivos (como Nat).
    Sintaxe no Lean 4:
      induction n with
      | zero =>
        -- caso base
        rfl
      | succ n ih =>
        -- passo indutivo (ih é a hipótese de indução)
        rw [Nat.add_succ, ih]
    """,
        "omega": """
    Tática `omega`:
    Provador automático de aritmética linear para inteiros e naturais (Nat/Int).
    Resolve equações e inequações lineares com +, -, *, constantes e variáveis.
    Exemplo:
      theorem t (a b : Nat) : a + b = b + a := by
        omega
    """,
        "simp": """
    Tática `simp`:
    Simplifica o alvo aplicando regras de reescrita padrão e lemas marcados com @[simp].
    Exemplo:
      simp
      simp [Nat.add_comm]
    """,
        "rfl": """
    Tática `rfl` (reflexivity):
    Fecha metas onde ambos os lados são identicamente iguais por definição (definitional equality).
    Exemplo:
      theorem t : 2 + 2 = 4 := by
        rfl
    """