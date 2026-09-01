"""IA Brasil — Prompts (templates versionados) da assistência LLM local.

Cada template referencia ``PROMPT_VERSION`` para rastreabilidade: a versão
de prompt/modelo usada é registrada nas saídas (ver ``schemas.py``).
"""

from __future__ import annotations

PROMPT_VERSION = "1.0.0"

# Limite de caracteres do texto enviado ao LLM (janela de contexto pequena).
MAX_TEXT_CHARS = 8000

_EXTRACT_JSON_SCHEMA = """{
  "indicadores": [
    {
      "nome": "Nome do indicador",
      "valor": 123.4,
      "unidade": "unidades",
      "tipo": "resultado | produto | impacto",
      "trecho_citado": "citação literal do texto",
      "fonte_url": "URL da fonte ou null"
    }
  ],
  "fonte_url": "URL da fonte ou null"
}"""

EXTRACT_INDICATORS_SYSTEM = (
    "Você é um analista de políticas públicas de inteligência artificial no "
    "Brasil. Seu trabalho é ASSISTIR a análise humana, nunca substituí-la. "
    "Você NUNCA inventa dados: toda informação de saída deve estar ancorada "
    "em uma citação literal do texto fornecido. "
    f"Versão do prompt: {PROMPT_VERSION}. "
    "Responda APENAS com um objeto JSON válido, sem texto adicional, no formato:\n"
    + _EXTRACT_JSON_SCHEMA
    + "\nRegras: 'trecho_citado' deve ser uma citação LITERAL (transcrição "
    "exata) presente no texto; se não houver trecho, não inclua o indicador."
)

EXTRACT_INDICATORS_TEMPLATE = """Extraia os indicadores, métricas e metas do seguinte texto público.

FONTE: {fonte_url}

TEXTO:
{texto}

Responda apenas com o JSON no formato especificado no system prompt."""


def build_extract_prompt(texto: str, fonte_url: str | None) -> str:
    """Monta o prompt de extração assistida de indicadores.

    Args:
        texto: Texto da fonte (truncado para a janela do modelo).
        fonte_url: URL da fonte (registrada nas citações).

    Returns:
        Prompt pronto para envio ao LLM.
    """
    return EXTRACT_INDICATORS_TEMPLATE.format(
        texto=texto[:MAX_TEXT_CHARS],
        fonte_url=fonte_url or "não informada",
    )


_SUMMARIZE_JSON_SCHEMA = """{
  "resumo": "resumo objetivo e fiel ao texto (máx. 300 caracteres)",
  "trecho_citado": "citação literal do texto que sustenta o resumo"
}"""

SUMMARIZE_SYSTEM = (
    "Você é um assistente de análise de evidências públicas. Resuma de forma "
    "objetiva e fiel, ancorando o resumo em uma citação literal do texto. "
    f"Versão do prompt: {PROMPT_VERSION}. "
    "Responda APENAS com um objeto JSON válido, sem texto adicional, no formato:\n"
    + _SUMMARIZE_JSON_SCHEMA
    + "\nRegras: resumo sem invenção; 'trecho_citado' é transcrição exata do texto."
)

SUMMARIZE_TEMPLATE = """Resuma a evidência abaixo em português, com citação da fonte.

TÍTULO: {titulo}
FONTE: {fonte_url}

TEXTO:
{texto}

Responda apenas com o JSON no formato especificado no system prompt."""


def build_summarize_prompt(titulo: str, texto: str, fonte_url: str | None) -> str:
    """Monta o prompt de resumo assistido de uma evidência.

    Args:
        titulo: Título da evidência (contexto).
        texto: Texto da evidência (truncado).
        fonte_url: URL da fonte (registrada na citação).

    Returns:
        Prompt pronto para envio ao LLM.
    """
    return SUMMARIZE_TEMPLATE.format(
        titulo=titulo or "Sem título",
        texto=texto[:MAX_TEXT_CHARS],
        fonte_url=fonte_url or "não informada",
    )


_CONTRADICTION_JSON_SCHEMA = """{
  "is_contradiction": true,
  "razao": "explicação objetiva de por que as claims são incompatíveis"
}"""

CONTRADICTION_SYSTEM = (
    "Você é um analista de evidências públicas. Compare duas claims e decida "
    "se elas são INCOMPATÍVEIS (ex.: promessa/execução, afirmação/negação "
    "sobre o mesmo fato). Você propõe candidatos para revisão humana — nunca "
    "decide em definitivo e nunca altera status. "
    f"Versão do prompt: {PROMPT_VERSION}. "
    "Responda APENAS com um objeto JSON válido, no formato:\n" + _CONTRADICTION_JSON_SCHEMA
)

CONTRADICTION_TEMPLATE = """Compare as duas claims abaixo e indique se são contraditórias.

CLAIM A (tipo: {tipo_a}):
{texto_a}

CLAIM B (tipo: {tipo_b}):
{texto_b}

Responda apenas com o JSON no formato especificado no system prompt."""


def build_contradiction_prompt(
    texto_a: str,
    tipo_a: str | None,
    texto_b: str,
    tipo_b: str | None,
) -> str:
    """Monta o prompt de julgamento de contradição entre duas claims.

    Args:
        texto_a: Texto da claim A.
        tipo_a: Tipo da claim A (promessa/anuncio/execucao/entrega/resultado).
        texto_b: Texto da claim B.
        tipo_b: Tipo da claim B.

    Returns:
        Prompt pronto para envio ao LLM.
    """
    return CONTRADICTION_TEMPLATE.format(
        texto_a=texto_a[:2000],
        tipo_a=tipo_a or "não classificado",
        texto_b=texto_b[:2000],
        tipo_b=tipo_b or "não classificado",
    )
