"""Guardrails de entrada e saída implementados como nós do grafo LangGraph.

Por quê: um assistente de provas com acesso a compilador e rede (MCP fetch) está
sujeito a riscos concretos do domínio:
1. Entrada — Prompt Injection e burla do verificador (pedir `sorry`, `IO.Process`,
   `unsafe`, ou mandar o modelo ignorar regras e retornar ACEITA sem provar).
2. Entrada — Pedidos fora do escopo (desvio para culinária, entretenimento, etc.).
3. Saída — Vazamento de credenciais (`GROQ_API_KEY`) ou instruções internas de sistema.
4. Saída — Alucinação de veredito (afirmar que o Lean aceitou uma prova quando `aceita=False`).
"""
import re
from typing import Tuple

PADROES_INJECTION = [
    re.compile(r"ignore\s+(all\s+)?(previous\s+)?(system\s+)?instructions", re.IGNORECASE),
    re.compile(r"forget\s+(everything|all|your)\s+(above|instructions|rules)", re.IGNORECASE),
    re.compile(r"esque[çc]a\s+(todas\s+as\s+)?instru[çc][õo]es", re.IGNORECASE),
    re.compile(r"(developer\s+mode|jailbreak|system\s*prompt\s*override)", re.IGNORECASE),
    re.compile(r"\b(rm\s+-rf|sudo\s+|chmod\s+777|curl\s+.*?\|\s*sh|os\.system|subprocess)\b", re.IGNORECASE),
    re.compile(r"retorne\s+apenas\s+['\"]?ACEITA['\"]?", re.IGNORECASE),
    re.compile(r"finja\s+que\s+(o\s+Lean\s+)?aceitou", re.IGNORECASE),
    re.compile(r"(burl[ae]|use\s+sorry\s+para\s+passar|adicione\s+um\s+axiom\s+falso)", re.IGNORECASE),
    re.compile(r"\b(IO\.Process|IO\.FS|System\.FilePath|unsafePerformIO)\b", re.IGNORECASE),
]

TERMOS_DOMINIO = {
    "lean", "lean4", "teorema", "teoremas", "prova", "provas", "provar", "demonstre",
    "demonstrar", "demonstracao", "demonstração", "hipotese", "hipótese", "hipoteses",
    "meta", "metas", "tatica", "tática", "taticas", "táticas", "intro", "rw", "rewrite",
    "simp", "omega", "induction", "inducao", "indução", "rfl", "cases", "exact", "apply",
    "decide", "have", "prop", "nat", "int", "list", "bool", "matematica", "matemática",
    "logica", "lógica", "soma", "dobro", "rev", "axioma", "funcao", "função", "funcoes",
    "funções", "definicao", "definição", "definicoes", "definições", "check", "print",
    "eval", "reduce", "mcp", "skill", "skills", "rag", "fetch", "url", "https", "lean-lang",
    "mathlib", "lema", "lemas", "assinatura", "erro", "erros", "pattern", "target",
    "comutatividade", "associatividade", "contraexemplo", "refutar", "negacao", "negação",
    "arquivo", "arquivos", "repositorio", "repositório", "projeto", "guia", "documentacao",
    "documentação", "markdown", "codigo", "código", "recursiva", "recursivo",
    "indutiva", "indutivo",
}

SAUDACOES = {"oi", "ola", "olá", "bom", "dia", "tarde", "noite", "ajuda"}

PADROES_VAZAMENTO = [
    re.compile(r"gsk_[A-Za-z0-9_-]{20,}", re.IGNORECASE),
    re.compile(r"sk-[A-Za-z0-9_-]{20,}", re.IGNORECASE),
    re.compile(r"(?:api[_-]?key|secret|token)\s*[:=]\s*['\"]?[A-Za-z0-9_-]{16,}", re.IGNORECASE),
    re.compile(r"GROQ_API_KEY\s*=\s*\S+", re.IGNORECASE),
]

FRAGMENTOS_PROMPT_INTERNO = (
    "INTERPRETAR_SYSTEM",
    "SYSTEM_AGENTE",
    "Você classifica mensagens enviadas a um assistente de provas",
)


def checar_guardrail_entrada(texto: str) -> Tuple[bool, str]:
    """Avalia a entrada do usuário contra prompt injection, burla ao Lean e desvio de escopo."""
    if not texto or not texto.strip():
        return False, "Entrada vazia fornecida."

    texto_limpo = texto.strip()

    # 1. Risco de Prompt Injection / manipulação do compilador Lean
    for padrao in PADROES_INJECTION:
        if padrao.search(texto_limpo):
            return False, (
                "GUARDRAIL DE ENTRADA ATIVADO (Risco: Prompt Injection / Violação de Segurança).\n"
                "Sua mensagem contém instruções para ignorar regras, executar comandos inseguros "
                "ou burlar a verificação formal do Lean 4. O pedido foi bloqueado."
            )

    # 2. Risco de Pedido Fora do Escopo do Domínio
    palavras = re.findall(r"[a-zA-Z0-9_áéíóúâêîôûãõçÁÉÍÓÚÂÊÎÔÛÃÕÇ-]+", texto_limpo.lower())
    if len(palavras) >= 4:
        intersecao = set(palavras) & TERMOS_DOMINIO
        # Também aceita expressões matemáticas simbólicas como `a + b = b + a` ou `∀ n`
        tem_simbolo_matematico = any(s in texto_limpo for s in ("∀", "∃", "∧", "∨", "→", "↔", "¬", "⊢", ":="))
        if not intersecao and not tem_simbolo_matematico:
            return False, (
                "GUARDRAIL DE ENTRADA ATIVADO (Risco: Pedido Fora do Escopo).\n"
                "Este assistente atua exclusivamente com matemática formal, lógica e Lean 4. "
                "Reformule sua mensagem com foco em teoremas, táticas ou documentação de Lean."
            )

    return True, ""


def checar_guardrail_saida(
    texto: str,
    aceita: bool = False,
    refutada: bool = False,
    intencao: str = "",
) -> Tuple[bool, str]:
    """Higieniza segredos na saída e audita a integridade do veredito formal."""
    if not texto:
        return True, texto

    texto_sanitizado = texto

    # 1. Proteção contra vazamento de chaves / credenciais
    for padrao in PADROES_VAZAMENTO:
        if padrao.search(texto_sanitizado):
            texto_sanitizado = padrao.sub("[REDACTED_API_KEY]", texto_sanitizado)

    # 2. Proteção contra vazamento literal de instruções internas de sistema
    for frag in FRAGMENTOS_PROMPT_INTERNO:
        if frag in texto_sanitizado:
            texto_sanitizado = texto_sanitizado.replace(frag, "[CONTEUDO_INTERNO_PROTEGIDO]")

    # 3. Integridade do veredito: nunca afirmar sucesso sem aprovação real do compilador
    if intencao == "provar" and not aceita and not refutada:
        afirmacoes_falsas = (
            "o teorema foi provado com sucesso",
            "o lean aprovou a prova",
            "prova aceita pelo compilador",
        )
        texto_lower = texto_sanitizado.lower()
        if any(f in texto_lower for f in afirmacoes_falsas) and "não consegui" not in texto_lower:
            texto_sanitizado = (
                "[ALERTA DO GUARDRAIL DE SAÍDA: Integridade de Verificação]\n"
                "O compilador Lean 4 NÃO aprovou a prova neste turno; o teorema permanece não provado.\n\n"
                + texto_sanitizado
            )

    return True, texto_sanitizado
