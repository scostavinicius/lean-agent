---
name: diagnostico_erros
description: Procedimento de 5 etapas para classificar erros do compilador Lean 4 (unsolved goals, type mismatch, unknown identifier, tactic failed), decidir entre RAG/MCP/refutação e corrigir provas.
---

# Skill: Diagnóstico Sistemático de Erros no Lean 4

## Quando Utilizar
- Sempre que `testar_tatica` retornar `RECUSADA`, especialmente após uma tentativa direta falhar ou quando surgir erro de sintaxe, identificador desconhecido ou suspeita de teorema falso.

## Procedimento em 5 Etapas

### Etapa 1: Classificar o Erro do Parser
Identifique o tipo reportado por `testar_tatica`:
1. `unknown identifier`: lema ou função inexistente no escopo.
2. `type mismatch`: termos com tipos ou orientações incompatíveis.
3. `tactic failed` (ex: `did not find instance of pattern`): `rw` ou `apply` não encontrou o padrão na meta.
4. `unsolved goals`: faltou fechar algum ramo da prova (ex: caso `succ` ou meta residual).

### Etapa 2: Inspecionar Hipóteses e Objetivo (`⊢`)
1. Leia `hipoteses` e `objetivo` devolvidos pelo parser.
2. Confira se há premissas ainda não introduzidas com `intro` ou conectivos `∧` / `∨` que precisam de `cases` ou `constructor`.

### Etapa 3: Investigar com Ferramentas de Apoio (RAG e MCP)
- **Se `unknown identifier`:** consulte o tipo exato com `mcp_lean_consultar` (`#check nome_lema`) ou busque na documentação oficial com `consultar_documentacao` (usando termos técnicos em inglês).
- **Se `did not find instance of pattern` em `rw [lema]`:** verifique se a igualdade deve ser aplicada da direita para a esquerda com `rw [← lema]`.
- **Se suspeitar que o teorema é falso** (ex: subtração em `Nat` como `a - b + b = a` ou desigualdade falsa para `n = 1`): teste um contraexemplo concreto usando `testar_negacao` (ex: `intro h` seguido de `exact absurd (h 0 1) (by decide)`).

### Etapa 4: Aplicar Correção Mínima
Modifique apenas o passo que travou em vez de reescrever do zero sem justificativa:
- Troque `rw [L]` por `rw [← L]`.
- Substitua `rfl` por `omega` ou `simp` em igualdades aritméticas que não fecham por redução definicional.
- Para funções recursivas que não reduzem, carregue também a skill `inducao_estruturada`.

### Etapa 5: Revalidar e Nunca Repetir Erros
Submeta a nova prova a `testar_tatica` (ou a refutação a `testar_negacao`) e confira se o objetivo (`⊢`) avançou. Nunca reenvie exatamente a mesma prova já recusada.
