# Guia Rápido de Táticas do Lean 4

## intro
Usada para introduzir variáveis ou hipóteses no contexto local a partir de implicações (`→`) ou quantificadores universais (`∀`).
```lean
theorem exemplo (p q : Prop) : p → q → p := by
  intro hp hq
  exact hp
```

## rw (rewrite)
Substitui termos usando igualdades provadas ou hipóteses. Use colchetes.
Para reescrever no sentido inverso, use a seta para a esquerda: `rw [← lema]`.
```lean
rw [Nat.add_zero]
rw [Nat.add_succ, ih]
```

## induction
Usada para prova por indução matemática sobre tipos indutivos (como Nat).
Sintaxe no Lean 4:
```lean
induction n with
| zero =>
  -- caso base
  rfl
| succ n ih =>
  -- passo indutivo (ih é a hipótese de indução)
  rw [Nat.add_succ, ih]
```

## omega
Provador automático de aritmética linear para inteiros e naturais (`Nat`/`Int`).
Resolve equações e inequações lineares com `+`, `-`, `*`, constantes e variáveis.
```lean
theorem t (a b : Nat) : a + b = b + a := by
  omega
```

## simp
Simplifica o alvo aplicando regras de reescrita padrão e lemas marcados com `@[simp]`.
```lean
simp
simp [Nat.add_comm]
```

## rfl (reflexivity)
Fecha metas onde ambos os lados são identicamente iguais por definição (definitional equality).
```lean
theorem t : 2 + 2 = 4 := by
  rfl
```
