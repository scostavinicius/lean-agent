"""Verificação no Lean: monta o arquivo .lean e roda o compilador.

O agente produz só as táticas. O arquivo, com as definições e o cabeçalho
`theorem alvo ... := by`, é montado aqui, sempre do mesmo jeito. Quem dá a
palavra final é o Lean, não o modelo.
"""
import os
import shutil
import subprocess
from pathlib import Path

# Por quê: o elan instala o Lean em ~/.elan/bin, que nem sempre está no PATH do
# processo (Colab, Streamlit iniciado por atalho). Sem isso o subprocess não acha o `lean`.
if shutil.which("lean") is None:
    os.environ["PATH"] = os.path.expanduser("~/.elan/bin") + os.pathsep + os.environ["PATH"]

# Os arquivos ficam em workspace/ para não se misturarem com os do repositório.
PASTA_LEAN = Path("workspace")

# O timeout existe porque uma tática como simp pode entrar em laço e travar o agente (aula 07).
TIMEOUT_LEAN = 60  # segundos

# Entra no topo de todo arquivo .lean, porque TESTE7, TESTE8 e TESTE9 usam funções
# que o Lean não conhece (conferir com o enunciado da tarefa).
DEFINICOES_LEAN = """def dobro : Nat → Nat
  | 0     => 0
  | n + 1 => dobro n + 2

def soma : Nat → Nat
  | 0     => 0
  | n + 1 => soma n + (n + 1)

def rev {α : Type} : List α → List α
  | []      => []
  | x :: xs => rev xs ++ [x]"""


def montar_cabecalho(enunciado: str) -> str:
    """Devolve o que vem depois de `theorem alvo`, pondo o ":" quando o enunciado não tem binders.

    "(a b : Nat) : a + b = b + a" já traz o ":" depois dos binders. Já
    "∃ n : Nat, n * n = 49" é só o tipo, e sem o ":" o Lean acusa erro de sintaxe
    no cabeçalho antes de olhar a prova.
    """
    if enunciado.lstrip().startswith(("(", "{", "[", "⦃", ":")):
        return enunciado
    return ": " + enunciado


def get_arquivo_lean(enunciado: str, prova: str, nome_arquivo: str) -> None:
    """Gera {nome_arquivo}.lean na pasta de trabalho, com as definições e o teorema."""
    PASTA_LEAN.mkdir(exist_ok=True)
    prova_indentada = "\n".join("  " + linha for linha in prova.strip().splitlines())
    codigo = f"{DEFINICOES_LEAN}\n\ntheorem alvo {montar_cabecalho(enunciado)} := by\n{prova_indentada}\n"
    (PASTA_LEAN / f"{nome_arquivo}.lean").write_text(codigo, encoding="utf-8")


def ler_arquivo_lean(nome_arquivo: str) -> str:
    """Lê um arquivo .lean da pasta de trabalho."""
    return (PASTA_LEAN / f"{nome_arquivo}.lean").read_text(encoding="utf-8")


def test_prova(enunciado: str, prova: str, nome_arquivo: str = "Prova") -> tuple[bool, str]:
    """Roda o Lean em `theorem alvo <enunciado> := by <prova>` e devolve (aceita, saída do Lean).

    Só conta como aceita se compilar sem erro e sem `sorry`.
    """
    get_arquivo_lean(enunciado, prova, nome_arquivo)
    arquivo = nome_arquivo + ".lean"
    try:
        # encoding explícito: no Windows o padrão é cp1252, que não decodifica ⊢, ∧, →.
        resultado = subprocess.run(
            ["lean", arquivo], cwd=PASTA_LEAN, capture_output=True, text=True,
            encoding="utf-8", errors="replace", timeout=TIMEOUT_LEAN,
        )
    except subprocess.TimeoutExpired:
        # A mensagem imita o formato do Lean para o parsear tratá-la como erro.
        return False, f"{arquivo}: error: o Lean passou de {TIMEOUT_LEAN} s e foi interrompido"

    saida = resultado.stdout + resultado.stderr
    aceita = resultado.returncode == 0 and "sorry" not in saida and "sorry" not in prova

    return aceita, saida
