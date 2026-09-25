
---

### 1. Ferramenta de Aplicação de Teoremas Padrão (Heurísticas Prontas)

* **O que faz:** Um middleware que testa automaticamente estratégias conhecidas (como chamar `omega`, `simp`, `rfl` ou lemas básicos de igualdade) antes de acionar o LLM.
* **Por que é ótima:** Economiza tempo de computação e chamadas de API em teoremas triviais de aritmética e álgebra básica. O LLM deve ser reservado apenas para os momentos em que o caminho lógico precisa de criatividade (como induções complexas).

### 2. Parser da Saída de Erro do Lean (Filtragem de Logs)

* **O que faz:** Uma função Python que lê o log bruto do compilador do Lean e extrai apenas o que importa: **as hipóteses ativas** e a **meta atual ($\vdash$)**.
* **Por que é ótima:** Os logs do Lean vêm cheios de ruídos de compilação. Passar um texto limpo focando no "objetivo atual" faz a taxa de acerto do LLM subir drasticamente, evitando alucinações causadas por excesso de tokens irrelevantes.

### 3. Consulta de Teoremas/Mathlib (RAG ou Busca Local)

* **O que faz:** Uma base de dados ou função de busca onde o agente pode pesquisar nomes de teoremas da biblioteca padrão do Lean (Mathlib) por palavras-chave (ex: buscar lemas relacionados a comutatividade de naturais).
* **Por que é ótima:** O maior calcanhar de Aquiles de LLMs em provas formais é inventar nomes de teoremas que não existem (ex: chutar `Nat.add_comm_custom`). Dar ao agente uma ferramenta de busca reduz erros de compilação por nomes incorretos.

### 4. Memória do Agente (Histórico de Tentativas)

* **O que faz:** Uma estrutura de dados que registra o histórico de táticas que **já foram tentadas e falharam** na mesma prova, além de registrar estratégias bem-sucedidas em teoremas anteriores.
* **Por que é ótima:** Impede que o agente entre em loops infinitos, tentando exatamente a mesma tática incorreta repetidas vezes. A memória permite que ele analise: *"A tática X falhou no passo anterior com o erro Y, logo preciso tentar uma abordagem diferente (como indução)"*.

### 5. Análise de Fotos para Transcrição em Lean (Visão Computacional)

* **O que faz:** Permitir que o agente receba uma imagem (como uma foto tirada de um livro de matemática, uma lousa ou um rascunho em papel) e use a capacidade multimodal do Gemini para convertê-la em um enunciado formal em Lean 4.
* **Por que é ótima:** É um diferencial espetacular! Em vez de ter que digitar equações matemáticas complexas manualmente em formato de texto, você simplesmente tira foto de um exercício e o agente traduz para o código do Lean para começar a provar.

---

### Por onde começar? (Ordem Sugerida de Implementação)

Para não sobrecarregar o desenvolvimento de uma só vez, recomendo seguir esta ordem lógica:

1. **Passo 1 (Parser de Erros):** Facilita a vida do LLM imediatamente, entregando logs limpos. [X]
2. **Passo 2 (Aplicação de Heurísticas/Teoremas Padrão):** Resolve os casos fáceis sem gastar tokens.[x]
3. **Passo 3 (Memória do Agente):** Evita repetição de erros no loop iterativo.  [X]

4. **Passo 4 (Consulta à Mathlib):** Melhora a precisão de comandos complexos.
5. **Passo 5 (Análise de Fotos):** O toque final de usabilidade para importar teoremas visuais.

# posterior:

### 1. Busca em Árvore (Tree Search / Backtracking)

* **O que faz:** Em vez de seguir um caminho linear (tenta $\rightarrow$ erra $\rightarrow$ corrige o mesmo arquivo), o agente cria **ramificações (branches)**. Se em um determinado passo houver duas táticas plausíveis (`omega` ou `induction`), o agente explora ambas em paralelo. Se um caminho falhar completamente, ele faz um *backtracking* (volta atrás) para um estado anterior válido e tenta a outra rota.
* **Por que é matador:** Evita que o agente fique preso em um beco sem saída lógico de onde ele não consegue retornar sozinho.

### 2. Decomposição Automática de Metas (`have` Statements)

* **O que faz:** Ensinar o agente a quebrar teoremas complexos em pedaços menores. Quando ele percebe que o objetivo principal é muito difícil, ele próprio escreve um sub-teorema intermediário (`have h : ... := by ...`), prova esse pedaço primeiro, e depois usa o resultado para fechar a prova principal.
* **Por que é matador:** É exatamente isso que matemáticos humanos fazem. Dividir para conquistar reduz a complexidade que o LLM precisa processar de uma só vez.

### 3. Geração Paralela com Teste de Múltiplas Hipóteses (Self-Consistency)

* **O que faz:** Quando o Lean retorna um erro, o agente pede para o LLM gerar **3 a 5 opções diferentes de correção** em uma única chamada ou em paralelo. Em seguida, ele testa todas elas no Lean de forma sequencial.
* **Por que é matador:** Se a primeira opção falhar, a segunda ou a terceira podem passar imediatamente, economizando rodadas inteiras do loop de feedback.

### 4. Integração com o LSP (Language Server Protocol) do Lean

* **O que faz:** Em vez de compilar o arquivo inteiro via `subprocess` a cada alteração, o agente se comunica diretamente com o servidor de linguagem do Lean que roda em segundo plano no VS Code.
* **Por que é matador:** É muito mais rápido e permite inspecionar o estado exato das variáveis linha por linha quase em tempo real, sem o overhead de reprocessar todo o arquivo do zero.

---