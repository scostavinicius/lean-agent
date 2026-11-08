"""Resumo do log do Lean para o modelo.

O log do Lean tem ruído. O modelo recebe só o primeiro erro, as hipóteses e o
objetivo (⊢), porque é o harness que decide quanto o agente enxerga (aula 07).
O parser falha em silêncio (devolve um dicionário errado, sem exceção), por isso
ele tem testes em tests/test_parser.py.
"""
import re

CABECALHO_MENSAGEM = re.compile(r"^\S+?\.lean(?::\d+:\d+)?: (error|warning|info): ", re.MULTILINE)


def separar_mensagens(texto_log: str) -> list[tuple[str, str]]:
    """Quebra o log em mensagens (gravidade, texto), uma para cada `arquivo:linha:coluna: gravidade:`."""
    cabecalhos = list(CABECALHO_MENSAGEM.finditer(texto_log))
    mensagens = []
    for atual, seguinte in zip(cabecalhos, cabecalhos[1:] + [None]):
        fim = seguinte.start() if seguinte else len(texto_log)
        mensagens.append((atual.group(1), texto_log[atual.end():fim].strip()))
    return mensagens


def eh_linha_de_contexto(linha: str) -> bool:
    """Hipótese (`nome : tipo`), rótulo `case ...` ou continuação indentada de uma hipótese."""
    return bool(re.match(r"\S[^:]*? :(\s|$)", linha)) or linha.startswith(("case ", " ", "\t"))


def extrair_objetivo(texto: str) -> tuple[str, str, str]:
    """Separa uma mensagem de erro em (explicação, hipóteses, objetivo).

    O Lean termina a mensagem com o estado da prova: as hipóteses, uma por linha,
    e o objetivo depois de ⊢. Com vários objetivos, fica só o primeiro.
    """
    linhas = texto.splitlines()
    i_meta = next((i for i, linha in enumerate(linhas) if linha.startswith("⊢")), None)
    if i_meta is None:
        return texto.strip(), "", ""

    # O objetivo pode continuar nas linhas seguintes, indentadas.
    fim = i_meta + 1
    while fim < len(linhas) and linhas[fim].startswith((" ", "\t")):
        fim += 1
    objetivo = "\n".join([linhas[i_meta][1:].strip()] + [linha.strip() for linha in linhas[i_meta + 1:fim]])

    # As hipóteses são as linhas logo acima do ⊢, até uma linha em branco ou de texto.
    inicio = i_meta
    while inicio > 0 and eh_linha_de_contexto(linhas[inicio - 1]):
        inicio -= 1
    hipoteses = "\n".join(linhas[inicio:i_meta]).strip()
    explicacao = "\n".join(linhas[:inicio]).strip()
    return explicacao, hipoteses, objetivo


def parsear(texto_log: str) -> dict[str, str]:
    """Resume a saída do Lean em tipo, mensagem, hipóteses e objetivo do primeiro erro.

    Erro tem prioridade sobre o aviso de `sorry`: quando os dois aparecem, o que
    o modelo precisa consertar primeiro é o erro.
    """
    mensagens = separar_mensagens(texto_log)
    erros = [texto for gravidade, texto in mensagens if gravidade == "error"]

    if erros:
        explicacao, hipoteses, objetivo = extrair_objetivo(erros[0])
        if len(erros) > 1:
            explicacao += f"\n(e mais {len(erros) - 1} erro(s) depois deste)"
        return {"tipo": "erro_compilacao", "mensagem_limpa": explicacao,
                "hipoteses": hipoteses, "objetivo": objetivo}

    if any(gravidade == "warning" and "sorry" in texto for gravidade, texto in mensagens):
        return {"tipo": "sorry_pendente",
                "mensagem_limpa": "A prova contém 'sorry' e precisa ser completada.",
                "hipoteses": "", "objetivo": ""}

    return {"tipo": "desconhecido", "mensagem_limpa": texto_log.strip(), "hipoteses": "", "objetivo": ""}
