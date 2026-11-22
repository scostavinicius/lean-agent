"""RAG agêntico sobre os capítulos oficiais do livro Theorem Proving in Lean 4.

Por quê: em vez de injetar documentos fixos no prompt (o que estouraria o limite
de tokens por minuto da Groq) ou inventar lemas, o modelo decide quando consultar
a base, recebe trechos reais com a origem oficial e reformula a consulta em
termos técnicos do Lean 4 quando o resultado não basta.
"""
import math
import re
from dataclasses import dataclass
from pathlib import Path

from langchain_core.tools import tool

PASTA_DOCS = Path(__file__).parent / "docs_dominio"
TAMANHO_MAX_CHUNK = 900
LIMIAR_RELEVANCIA = 1.2


@dataclass
class TrechoDocumento:
    chunk_id: str
    arquivo: str
    secao: str
    origem: str
    fonte: str
    conteudo: str
    palavras: list[str]


def _tokenizar(texto: str) -> list[str]:
    """Extrai identificadores Lean (ex: Nat.add_comm) e palavras em minúsculas."""
    termos = re.findall(r"[A-Za-z0-9_]+(?:\.[A-Za-z0-9_]+)*", texto.lower())
    return [t for t in termos if len(t) > 1]


def _quebrar_em_chunks(secao_texto: str, tamanho_max: int = TAMANHO_MAX_CHUNK) -> list[str]:
    """Divide uma seção longa em blocos de até `tamanho_max` chars por parágrafos."""
    if len(secao_texto) <= tamanho_max:
        return [secao_texto]

    paragrafos = secao_texto.split("\n\n")
    blocos: list[str] = []
    atual: list[str] = []
    tamanho_atual = 0

    for paragrafo in paragrafos:
        p = paragrafo.strip()
        if not p:
            continue
        if atual and tamanho_atual + len(p) + 2 > tamanho_max:
            blocos.append("\n\n".join(atual))
            atual = [p]
            tamanho_atual = len(p)
        else:
            atual.append(p)
            tamanho_atual += len(p) + 2

    if atual:
        blocos.append("\n\n".join(atual))
    return blocos


class IndiceRAG:
    """Índice BM25 em memória sobre documentos reais do domínio Lean 4."""

    def __init__(self, pasta_docs: Path = PASTA_DOCS):
        self.pasta_docs = pasta_docs
        self.chunks: list[TrechoDocumento] = []
        self.doc_freq: dict[str, int] = {}
        self.total_docs: int = 0
        self.avg_doc_len: float = 1.0
        self._carregar_e_indexar()

    def _carregar_e_indexar(self) -> None:
        if not self.pasta_docs.exists():
            return

        chunks_temp: list[TrechoDocumento] = []
        total_len = 0

        for arquivo in sorted(self.pasta_docs.glob("*.md")):
            texto = arquivo.read_text(encoding="utf-8")
            linhas = texto.splitlines()

            origem = "Theorem Proving in Lean 4"
            fonte = "https://lean-lang.org/theorem_proving_in_lean4/"
            for linha in linhas[:6]:
                if linha.startswith("**Origem:**"):
                    origem = linha.split(":", 1)[1].lstrip("* ").strip()
                elif linha.startswith("**Fonte Oficial:**"):
                    fonte = linha.split(":", 1)[1].lstrip("* ").strip()

            # Divide por cabeçalhos Markdown (# ou ##)
            secoes = re.split(r"\n(?=#{1,2}\s+)", texto)
            for idx_sec, secao_bruta in enumerate(secoes):
                secao_limpa = secao_bruta.strip()
                if not secao_limpa or secao_limpa.startswith("**Origem:**"):
                    continue
                primeira_linha = secao_limpa.splitlines()[0]
                nome_secao = primeira_linha.lstrip("# ").strip() if primeira_linha.startswith("#") else "Introdução"

                for idx_bloco, bloco in enumerate(_quebrar_em_chunks(secao_limpa)):
                    palavras = _tokenizar(bloco)
                    if len(palavras) < 5:
                        continue
                    chunks_temp.append(
                        TrechoDocumento(
                            chunk_id=f"{arquivo.stem}_s{idx_sec}_b{idx_bloco}",
                            arquivo=arquivo.name,
                            secao=nome_secao,
                            origem=origem,
                            fonte=fonte,
                            conteudo=bloco,
                            palavras=palavras,
                        )
                    )
                    total_len += len(palavras)

        self.chunks = chunks_temp
        self.total_docs = len(chunks_temp)
        self.avg_doc_len = (total_len / self.total_docs) if self.total_docs > 0 else 1.0

        self.doc_freq = {}
        for chunk in self.chunks:
            for palavra in set(chunk.palavras):
                self.doc_freq[palavra] = self.doc_freq.get(palavra, 0) + 1

    def buscar(self, consulta: str, top_k: int = 3) -> list[tuple[TrechoDocumento, float]]:
        """Retorna os trechos mais relevantes por pontuação BM25."""
        termos = _tokenizar(consulta)
        if not self.chunks or not termos:
            return []

        k1, b = 1.5, 0.75
        pontuacoes: list[tuple[TrechoDocumento, float]] = []

        for chunk in self.chunks:
            freqs: dict[str, int] = {}
            for w in chunk.palavras:
                freqs[w] = freqs.get(w, 0) + 1

            score = 0.0
            doc_len = len(chunk.palavras)
            for termo in termos:
                if termo in freqs:
                    tf = freqs[termo]
                    df = self.doc_freq.get(termo, 0)
                    idf = math.log(1.0 + (self.total_docs - df + 0.5) / (df + 0.5))
                    score += idf * (tf * (k1 + 1.0)) / (tf + k1 * (1.0 - b + b * (doc_len / self.avg_doc_len)))

            if score > 0.2:
                pontuacoes.append((chunk, score))

        pontuacoes.sort(key=lambda item: item[1], reverse=True)
        return pontuacoes[:top_k]


_INDICE_RAG = IndiceRAG()


def resumo_base_rag() -> dict:
    """Resumo da base indexada para exibição na interface e testes."""
    arquivos = sorted({c.arquivo for c in _INDICE_RAG.chunks})
    return {"arquivos": len(arquivos), "trechos": len(_INDICE_RAG.chunks), "nomes": arquivos}


@tool(parse_docstring=True)
def consultar_documentacao(consulta: str) -> str:
    """Consulta a base oficial do livro Theorem Proving in Lean 4 por táticas, lemas e exemplos.

    Por quê: os documentos originais estão em inglês. Se você buscar em português e a
    relevância for baixa, reformule a consulta com termos em inglês ou identificadores Lean
    (ex: 'induction Nat', 'Nat.add_comm', 'rewrite tactic', 'simplifier simp') e busque novamente.

    Args:
        consulta: palavras-chave em inglês ou nomes de táticas/lemas do Lean 4.
    """
    resultados = _INDICE_RAG.buscar(consulta, top_k=2)
    if not resultados or resultados[0][1] < LIMIAR_RELEVANCIA:
        return (
            f"Nenhum trecho suficientemente relevante encontrado para '{consulta}'.\n"
            "AÇÃO NECESSÁRIA (RAG agêntico): os documentos oficiais estão em inglês. "
            "Reformule a consulta usando termos técnicos de Lean 4 em inglês "
            "(ex: 'rewrite', 'induction', 'simplifier simp', 'Nat.add_comm', 'quantifiers', "
            "'inductive types') e chame `consultar_documentacao` novamente."
        )

    partes = [f"Resultados da documentação oficial para '{consulta}':\n"]
    for i, (chunk, score) in enumerate(resultados, start=1):
        partes.append(
            f"[{i}] Seção: {chunk.secao} (Relevância BM25: {score:.2f})\n"
            f"Origem: {chunk.origem}\n"
            f"Fonte: {chunk.fonte}\n"
            f"{chunk.conteudo}\n"
        )
    partes.append(
        "Se estes trechos ainda não responderem completamente, reformule a consulta com termos mais específicos e busque de novo."
    )
    return "\n---\n".join(partes)
