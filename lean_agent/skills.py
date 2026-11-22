"""Skills especializadas em SKILL.md, descobertas dinamicamente e carregadas sob demanda.

Por quê: colocar instruções detalhadas de todos os procedimentos no prompt do sistema
gastaria tokens em toda chamada (e a Groq limita tokens por minuto). Em vez disso,
apenas o catálogo (nome + descrição do frontmatter de cada SKILL.md) vai no sistema,
e o modelo chama `carregar_skill` apenas quando precisar seguir aquele roteiro.
"""
import re
from pathlib import Path
from typing import Annotated

import yaml
from langchain_core.messages import ToolMessage
from langchain_core.tools import InjectedToolCallId, tool
from langgraph.types import Command

PASTA_SKILLS = Path(__file__).parent.parent / "skills"


def _extrair_frontmatter(texto: str) -> tuple[dict, str]:
    """Separa o frontmatter YAML (--- ... ---) do corpo Markdown do SKILL.md."""
    casamento = re.match(r"^---\s*\n(.*?)\n---\s*\n(.*)$", texto, flags=re.DOTALL)
    if not casamento:
        return {}, texto
    meta = yaml.safe_load(casamento.group(1)) or {}
    return meta, casamento.group(2).strip()


def descobrir_skills(pasta_skills: Path = PASTA_SKILLS) -> dict[str, dict]:
    """Descobre todos os arquivos SKILL.md na pasta de skills e lê seu catálogo."""
    catalogo: dict[str, dict] = {}
    if not pasta_skills.exists():
        return catalogo

    for arquivo in sorted(pasta_skills.glob("*/SKILL.md")):
        texto = arquivo.read_text(encoding="utf-8")
        meta, corpo = _extrair_frontmatter(texto)
        nome = str(meta.get("name") or arquivo.parent.name).strip()
        descricao = str(meta.get("description") or "Skill especializada de Lean 4.").strip()
        catalogo[nome] = {
            "nome": nome,
            "descricao": descricao,
            "caminho": arquivo,
            "corpo": corpo,
        }
    return catalogo


CATALOGO_SKILLS = {nome: info["descricao"] for nome, info in descobrir_skills().items()}


def obter_catalogo_prompt(pasta_skills: Path = PASTA_SKILLS) -> str:
    """Formata o catálogo de skills para a mensagem de sistema."""
    skills = descobrir_skills(pasta_skills)
    if not skills:
        return ""
    linhas = [
        "## Catálogo de Skills (Carregamento sob Demanda)",
        "Quando a tarefa exigir um procedimento multi-etapas (indução ou diagnóstico de erros), "
        "chame `carregar_skill` antes de tentar no escuro:",
    ]
    for nome, info in skills.items():
        linhas.append(f"- `{nome}`: {info['descricao']}")
    return "\n".join(linhas)


def ler_conteudo_skill(nome_skill: str, pasta_skills: Path = PASTA_SKILLS) -> str | None:
    """Devolve o conteúdo completo do SKILL.md correspondente ao nome."""
    nome_limpo = nome_skill.strip().lower()
    skills = descobrir_skills(pasta_skills)
    if nome_limpo in skills:
        return skills[nome_limpo]["corpo"]
    return None


@tool(parse_docstring=True)
def carregar_skill(
    nome_skill: str,
    tool_call_id: Annotated[str, InjectedToolCallId],
) -> Command:
    """Carrega sob demanda as instruções completas de uma skill do catálogo para o rascunho.

    Args:
        nome_skill: nome da skill conforme o catálogo do sistema (ex: 'inducao_estruturada', 'diagnostico_erros').
    """
    skills = descobrir_skills()
    nome_limpo = nome_skill.strip().lower()
    if nome_limpo not in skills:
        resposta = (
            f"Skill '{nome_skill}' não encontrada.\n"
            f"Skills disponíveis no catálogo: {', '.join(skills.keys())}"
        )
        return Command(update={"rascunho": [ToolMessage(resposta, tool_call_id=tool_call_id)]})

    conteudo = skills[nome_limpo]["corpo"]
    resposta = (
        f"=== SKILL CARREGADA ({nome_limpo}) ===\n"
        f"Fonte: {skills[nome_limpo]['caminho'].name}\n\n"
        f"{conteudo}"
    )
    return Command(update={
        "skills_carregadas": [nome_limpo],
        "rascunho": [ToolMessage(resposta, tool_call_id=tool_call_id)],
    })
