"""Cliente HTTP para executar código Lean 4 remotamente via Web API (sem instalação local)."""
import os
import re

import httpx

LEAN_WEB_URL = os.environ.get(
    "LEAN_WEB_URL",
    "https://godbolt.org/api/compiler/lean_4_29_1/compile",
)
TIMEOUT_LEAN = 60  # segundos

DEFINICOES_LEAN = """def dobro : Nat → Nat
  | 0     => 0
  | n + 1 => dobro n + 2

def soma : Nat → Nat
  | 0     => 0
  | n + 1 => soma n + (n + 1)

def rev {α : Type} : List α → List α
  | []      => []
  | x :: xs => rev xs ++ [x]"""


def executar_lean_web(
    codigo: str,
    arquivo: str = "Prova.lean",
    timeout: int = TIMEOUT_LEAN,
) -> tuple[int, str]:
    """Compila e verifica código Lean 4 via API web e devolve (codigo_saida, log)."""
    payload = {
        "source": codigo,
        "options": {
            "userArguments": "",
            "compilerOptions": {"skipAsm": True},
        },
    }
    try:
        resposta = httpx.post(
            LEAN_WEB_URL,
            json=payload,
            headers={"Accept": "application/json"},
            timeout=timeout,
        )
        resposta.raise_for_status()
        dados = resposta.json()
    except httpx.TimeoutException:
        return 1, f"{arquivo}: error: o Lean passou de {timeout} s e foi interrompido"
    except (httpx.HTTPError, ValueError) as erro:
        return 1, (
            f"{arquivo}:1:0: error: falha ao consultar o Lean 4 na web "
            f"({type(erro).__name__}: {erro})"
        )

    if dados.get("timedOut"):
        return 1, f"{arquivo}: error: o Lean passou de {timeout} s e foi interrompido"

    codigo_saida = int(dados.get("code", 1))
    linhas = [
        item.get("text", "")
        for campo in ("stdout", "stderr")
        for item in (dados.get(campo) or [])
        if isinstance(item, dict)
    ]
    saida = re.sub(r"<source>", arquivo, "\n".join(linhas))
    return codigo_saida, saida


def lean_web_disponivel(timeout: int = 8) -> bool:
    """Verifica se a execução remota do Lean 4 na web está habilitada e acessível."""
    if os.environ.get("LEAN_WEB_OFFLINE") == "1":
        return False
    codigo_saida, _ = executar_lean_web("#check Nat.add_comm\n", "Healthcheck.lean", timeout=timeout)
    return codigo_saida == 0
