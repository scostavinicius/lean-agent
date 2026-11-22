---
name: inducao_estruturada
description: Metodologia de 5 etapas para decomposição e prova por indução matemática em tipos indutivos (Nat, List) e funções recursivas no Lean 4.
---

# Skill: Prova por Indução Estruturada em Lean 4

## Quando Utilizar
- Teoremas universais sobre `Nat` ou `List α` envolvendo definições recursivas (ex: `dobro`, `soma`, `rev`), nos quais táticas diretas (`rfl`, `omega`, `simp`) falham por não expandirem recursão.

## Procedimento em 5 Etapas

### Etapa 1: Identificar a Variável Indutiva e Generalizar Contexto
1. Identifique sobre qual variável a função recursiva faz casamento de padrões (ex: em `dobro n = 2 * n`, a recursão ocorre sobre `n`).
2. Se houver variáveis livres que mudam na chamada recursiva, mantenha-as quantificadas ou use `induction xs generalizing ...`.
3. Se o enunciado tiver implicações antes da variável, use `intro` até trazê-la ao contexto.

### Etapa 2: Abrir os Ramos Indutivos
Use a sintaxe estruturada com `with` do Lean 4:
- Para `Nat`:
  ```lean
  induction n with
  | zero => ...
  | succ n ih => ...
  ```
- Para `List α`:
  ```lean
  induction xs with
  | nil => ...
  | cons x xs ih => ...
  ```

### Etapa 3: Fechar o Caso Base (`zero` ou `nil`)
1. No ramo base, avalie a definição com `rfl` ou `simp only [nome_funcao]`.
2. Verifique com `testar_tatica` ou mantenha curto para o próximo passo.

### Etapa 4: Desdobrar Definição e Aplicar `ih` no Passo Indutivo
1. No ramo `succ n ih` (ou `cons x xs ih`), expanda apenas a função recursiva:
   `simp only [dobro]` ou `simp only [soma, Nat.mul_add, Nat.add_mul, Nat.mul_one, Nat.one_mul] at *`.
2. Se a reescrita exigir um lema intermediário (ex: `rev (ys ++ [x]) = x :: rev ys` para provar `rev (rev xs) = xs`), declare um lema auxiliar local com:
   ```lean
   have aux : ... := by
     induction ys with ...
   ```
3. Aplique a hipótese indutiva `ih` (via `rw [ih]` ou `simp [..., ih]`) e finalize contas lineares com `omega`.

### Etapa 5: Validar no Compilador Lean
1. Nunca deixe `sorry` em nenhum ramo.
2. Submeta a prova completa a `testar_tatica` e confirme que retornou `ACEITA`.
