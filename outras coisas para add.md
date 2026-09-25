  ### 1. Ferramentas (Tools) que dão Agência Real ao Agente Lean 4

  No Lean 4, um matemático humano não tenta chutar a prova inteira às cegas; ele inspeciona definições, testa casos e consulta lemas. O agente deve ter ferramentas para fazer o
  mesmo:

  #### A. Ferramenta #print (inspecionar_definicao)
  Você já tem o #check (que devolve o Tipo). Mas o #print revela como uma função ou tipo foi definido e seus axiomas de indução.
  • Exemplo de uso pelo agente: Para provar a + b = b + a, o modelo pode rodar #print Nat.add e descobrir que a adição foi definida recursivamente por Nat.add_zero e Nat.
  add_succ.
  • Implementação:
    @tool
    def inspecionar_definicao(simbolo: str) -> str:
        """Executa `#print <simbolo>` no Lean 4 para ver a definição de tipos, construtores ou lemas."""
        codigo = f"#print {simbolo}\n"
        Path("Print.lean").write_text(codigo, encoding="utf-8")
        res = subprocess.run(["lean", "Print.lean"], capture_output=True, text=True)
        return res.stdout + res.stderr


  #### B. Ferramenta de Guia/Documentação de Táticas (consultar_tatica)

  Modelos de linguagem frequentemente erram a sintaxe exata do Lean 4 (confundindo com Lean 3 ou inventando nomes de táticas). Ter um catálogo interno permite ao modelo
  consultar como aplicar cada tática:
  • O que faz: Se o Lean retornar erro em um induction, o agente chama consultar_tatica("induction") e recebe exemplos de sintaxe válida (induction a with | zero => ... | succ
  a ih => ...).
  • Implementação: Um dicionário local em Python mapeando táticas (intro, rw, apply, cases, induction, omega, simp, rfl) para seus templates e explicações sucintas.
  #### C. Ferramenta #eval (avaliar_expressao)

  • O que faz: Executa #eval <expressao>. Permite ao agente testar casos base ou verificar contraexemplos numéricos antes de tentar provar uma propriedade geral.
  • Exemplo: #eval (2 + 3) + 4 == 2 + (3 + 4) ajuda o modelo a confirmar a semântica da igualdade.

  #### D. Ferramenta de Busca de Lemas / Sugestões (sugerir_lemas)

  • O que faz: No Lean 4, quando não sabemos o nome exato do lema, usamos táticas de busca ou inspecionamos os lemas do módulo.
  • O agente pode ter uma ferramenta que busca no ambiente lemas que contêm certas palavras-chave (por exemplo, pesquisar por "add_comm", "add_assoc", "zero_add").
  ──────
  ### 2. Seria interessante colocar Memória nele?

  Sim, e é um dos mecanismos mais valorizados para esse tipo de tarefa!

  No seu notebook, a seção 2.5 Mecanismos pede expressamente:

  │ "Por exemplo, estado para não repetir tentativas e planejamento da prova em etapas. Requisito atendido: pelo menos 2 mecanismos com função real."

  Existem dois níveis de memória que transformam seu agente:

  #### Nível 1: Memória de Trabalho / Tentativas Falhas (Anti-Loop) — Indispensável

  • O problema sem memória: O LLM frequentemente entra em loop: tenta simp, falha com erro X; depois tenta rw [Nat.add_zero], falha com erro Y; e na 3ª iteração tenta simp
  novamente.
  • Como a memória resolve:
  O agente mantém uma lista de tentativas que já falharam:
    memoria_tentativas = [
        {"tatica": "simp", "erro": "simp made no progress"},
        {"tatica": "rw [Nat.add_zero]", "erro": "did not find instance"}
    ]
  Ao receber esse histórico, o prompt do agente ganha a instrução explícita: "Você já tentou as estratégias acima e elas falharam. Não repita nenhuma delas."

  #### Nível 2: Memória de Longo Prazo / Episódica (agentkit.memory)

  O próprio pacote agentkit já vem com as funções remember e recall baseadas em vetores/embeddings:

  • Como funciona na prática:
      1. Quando o agente consegue provar com sucesso um teorema (por exemplo, comutatividade da soma a + b = b + a usando indução), ele guarda na memória:
        remember(memoria, embeddings, text="Teorema add_comm provado com: induction a with ...")

      2. Quando você pedir para ele provar outro teorema semelhante (ex: (a + b) + c = a + (b + c) ou a * b = b * a), ele executa:
        exemplos_uteis = recall(memoria, embeddings, query=novo_enunciado, k=2)

      3. O agente recupera a prova anterior como um exemplo (few-shot) de sucesso. O modelo passa a "aprender" com os teoremas que ele próprio já resolveu!

  ──────
  ### Visão Geral da Arquitetura Ideal

  Com isso, o fluxo do seu agente passa a ser verdadeiramente agêntico:

    [Enunciado do Teorema]
            │
            ▼
       [AgentKit] ──── Consulta Memória ────► [Lembra de provas semelhantes passadas]
            │
            ├──► Executa `inspecionar_definicao` (#print Nat.add)
            ├──► Executa `consultar_tatica` (checa sintaxe da induction)
            ├──► Executa `test_prova` (testa o script de prova no Lean)
            │         ▲
            │         └── Lê o erro do compilador Lean
            ▼
    [Decide se para (Prova Aceita) ou tenta nova estratégia sem repetir erros da memória]

  Essa composição atende com sobra todos os critérios de ferramentas ativas, mecanismos de controle e agência autônoma exigidos no trabalho.
