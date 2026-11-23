"""Verificação no Lean via Web API: monta o código .lean e valida remotamente.

O agente produz só as táticas. O arquivo, com as definições e o cabeçalho
`theorem alvo ... := by`, é montado aqui e enviado para compilação remota na web
(sem necessidade de instalar Lean/elan localmente). Quem dá a palavra final é o Lean.
"""
from pathlib import Path

from .lean_web import DEFINICOES_LEAN, TIMEOUT_LEAN, executar_lean_web

# Os arquivos gerados ficam em workspace/ para não se misturarem com os do repositório.
PASTA_LEAN = Path("workspace")


def montar_cabecalho(enunciado: str) -> str:
    """Devolve o que vem depois de `theorem alvo`, pondo o ":" quando o enunciado não tem binders.

    "(a b : Nat) : a + b = b + a" já traz o ":" depois dos binders. Já
    "∃ n : Nat, n * n = 49" é só o tipo, e sem o ":" o Lean acusa erro de sintaxe
    no cabeçalho antes de olhar a prova.
    """
    if enunciado.lstrip().startswith(("(", "{", "[", "⦃", ":")):
        return enunciado
    return ": " + enunciado


def negar_enunciado(enunciado: str) -> str:
    """Escreve a negação do enunciado: os binders viram um ∀ dentro do ¬."""
    texto = enunciado.strip()
    fim, nivel = 0, 0
    for i, c in enumerate(texto):
        if c in "({[⦃":
            nivel += 1
        elif c in ")}]⦄":
            nivel -= 1
            if nivel == 0:
                fim = i + 1
        elif nivel == 0 and not c.isspace():
            break
    binders, corpo = texto[:fim].strip(), texto[fim:].strip().removeprefix(":").strip()
    return f"¬ ∀ {binders}, {corpo}" if binders else f"¬ ({corpo})"


def montar_codigo_lean(enunciado: str, prova: str) -> str:
    """Monta o código-fonte completo em Lean 4 com as definições e o teorema alvo."""
    prova_indentada = "\n".join("  " + linha for linha in prova.strip().splitlines())
    return f"{DEFINICOES_LEAN}\n\ntheorem alvo {montar_cabecalho(enunciado)} := by\n{prova_indentada}\n"


def get_arquivo_lean(enunciado: str, prova: str, nome_arquivo: str) -> str:
    """Gera {nome_arquivo}.lean na pasta de trabalho e devolve o código montado."""
    PASTA_LEAN.mkdir(exist_ok=True)
    codigo = montar_codigo_lean(enunciado, prova)
    (PASTA_LEAN / f"{nome_arquivo}.lean").write_text(codigo, encoding="utf-8")
    return codigo


def ler_arquivo_lean(nome_arquivo: str) -> str:
    """Lê um arquivo .lean da pasta de trabalho."""
    return (PASTA_LEAN / f"{nome_arquivo}.lean").read_text(encoding="utf-8")


def test_prova(enunciado: str, prova: str, nome_arquivo: str = "Prova") -> tuple[bool, str]:
    """Executa Lean 4 na web em `theorem alvo <enunciado> := by <prova>` e devolve (aceita, saída).

    Só conta como aceita se compilar sem erro e sem `sorry`.
    """
    codigo = get_arquivo_lean(enunciado, prova, nome_arquivo)
    arquivo = nome_arquivo + ".lean"
    returncode, saida = executar_lean_web(codigo, arquivo=arquivo, timeout=TIMEOUT_LEAN)
    aceita = returncode == 0 and "sorry" not in saida and "sorry" not in prova
    return aceita, saida
