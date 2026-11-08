"""O modelo de linguagem e a saída estruturada.

A tarefa proíbe a chave no repositório: ela vem da variável de ambiente
GROQ_API_KEY, ou de um arquivo .env fora do git (veja .env.example).
"""
import json
import logging
import os

from dotenv import load_dotenv
from langchain_core.language_models import BaseChatModel
from langchain_groq import ChatGroq
from pydantic import BaseModel

load_dotenv()
log = logging.getLogger(__name__)

MODELO = os.environ.get("LEAN_AGENT_MODELO", "openai/gpt-oss-120b")

# O raciocínio do gpt-oss também é token gerado e entra no limite. "low" gasta
# menos, "medium" é o padrão da Groq, e None não envia o parâmetro.
ESFORCO_RACIOCINIO = "low"

# Por quê: o plano gratuito da Groq limita o gpt-oss-120b a 8.000 tokens e 30
# pedidos por minuto. Esse 429 não é erro da prova: o SDK da Groq lê o
# retry-after da resposta, espera e tenta de novo, até este número de vezes.
# O limite diário (200.000 tokens) não se resolve esperando, e aí o erro sobe.
MAX_TENTATIVAS_API = 5


def criar_llm() -> ChatGroq:
    """O gpt-oss-120b pela Groq, com temperatura zero e o retry do 429 ligado."""
    if not os.environ.get("GROQ_API_KEY"):
        raise RuntimeError("defina GROQ_API_KEY no ambiente ou em um arquivo .env (veja .env.example)")

    # Por quê: no Git Bash com o conda ativo, o script de ativação do openssl aponta
    # SSL_CERT_FILE para <conda>/ssl/cacert.pem, que no Windows não existe (o arquivo
    # fica em Library/ssl). O httpx, usado pelo SDK da Groq, quebra ao abrir esse
    # caminho. Sem a variável ele usa os certificados do certifi, e o HTTPS continua verificado.
    certificados = os.environ.get("SSL_CERT_FILE")
    if certificados and not os.path.isfile(certificados):
        log.warning("SSL_CERT_FILE aponta para um arquivo que não existe (%s); usando os certificados do certifi",
                    certificados)
        del os.environ["SSL_CERT_FILE"]

    return ChatGroq(
        model=MODELO,
        temperature=0.0,
        max_tokens=2000,
        reasoning_effort=ESFORCO_RACIOCINIO if "gpt-oss" in MODELO else None,
        max_retries=MAX_TENTATIVAS_API,
    )


def gerar_estruturado(llm: BaseChatModel, mensagens: list, esquema: type[BaseModel]) -> BaseModel | None:
    """Pede ao modelo uma resposta no formato `esquema`. Devolve None se ele não colaborar.

    Usa json_schema em modo strict: a Groq restringe a geração ao schema, e o modelo
    não tem como esquecer um campo. Com function_calling, o gpt-oss deixava campos
    do Passo de fora e a Groq devolvia 400 em quase todo plano. Em modelos sem modo
    strict o ChatGroq ignora o parâmetro.

    O provedor ainda pode recusar a saída estruturada (aula 03). Aí o JSON é pedido
    no prompt e o primeiro objeto da resposta é validado pelo Pydantic.
    """
    try:
        return llm.with_structured_output(esquema, method="json_schema", strict=True).invoke(mensagens)
    except Exception as erro:
        log.warning("saída estruturada falhou (%s: %s); tentando JSON no prompt",
                    type(erro).__name__, str(erro)[:200])

    formato = (
        "\n\nResponda APENAS com JSON que siga este JSON Schema, sem cercas de código:\n"
        + json.dumps(esquema.model_json_schema(), ensure_ascii=False)
    )
    pedido = list(mensagens)
    pedido[-1] = type(pedido[-1])(content=pedido[-1].content + formato)
    try:
        resposta = llm.invoke(pedido).content
        inicio, fim = resposta.find("{"), resposta.rfind("}")
        return esquema.model_validate(json.loads(resposta[inicio:fim + 1]))
    except Exception as erro:
        log.warning("JSON no prompt também falhou (%s: %s)", type(erro).__name__, erro)
        return None
