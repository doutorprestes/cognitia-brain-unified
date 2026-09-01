"""IA Brasil — Serviço de assistência LLM local com citação obrigatória.

Fluxos:
- ``extract_indicators``: extração assistida de indicadores com citação;
- ``summarize_evidence``: resumo com fonte (citação obrigatória);
- ``find_contradictions``: candidatos a contradição entre claims (promessa vs
  execução etc.) com trechos citados.

Princípios:
- O LLM é ASSISTENTE: as funções retornam propostas/candidatos; nenhuma altera
  status ou persiste dados;
- Abstention: sem resposta válida do LLM, cai para heurística local
  determinística ou retorna ``None`` — nunca inventa.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

from loguru import logger

from src.modules.llm_assist.client import OllamaClient
from src.modules.llm_assist.prompts import (
    CONTRADICTION_SYSTEM,
    EXTRACT_INDICATORS_SYSTEM,
    PROMPT_VERSION,
    SUMMARIZE_SYSTEM,
    build_contradiction_prompt,
    build_extract_prompt,
    build_summarize_prompt,
)
from src.modules.llm_assist.schemas import (
    ClaimData,
    ContradictionCandidate,
    ContradictionJudgment,
    ExtractedIndicator,
    ExtractionResult,
    SummarizationResult,
)

if TYPE_CHECKING:
    from collections.abc import Sequence

    from src.core.db import Evidencia

# Heurística local (fallback) de extração de indicadores: número + unidade.
_METRIC_RE = re.compile(
    r"(?P<valor>\d[\d.,]*)\s*"
    r"(?P<unidade>bilh[oõ]es|bilh[aã]o|milh[oõ]es|milh[aã]o|mil|%|unidades?"
    r"|pessoas?|empresas?|institui[cç][oõ]es|profissionais?|centros?|escolas?"
    r"|hospitais?|projetos?|servidores?|munic[ií]pios?|estados?|vagas?|cursos?"
    r"|sistemas?|toneladas?|hectares?|km|MWp|MW)",
    re.IGNORECASE,
)

_PROMESSA_TIPOS = frozenset({"promessa", "anuncio"})
_EXECUCAO_TIPOS = frozenset({"execucao", "entrega", "resultado"})

_STOPWORDS = frozenset(
    {
        "a",
        "ao",
        "aos",
        "as",
        "até",
        "ate",
        "como",
        "com",
        "das",
        "de",
        "do",
        "dos",
        "e",
        "em",
        "entre",
        "foi",
        "ja",
        "já",
        "mais",
        "mil",
        "na",
        "nas",
        "no",
        "nos",
        "não",
        "nao",
        "o",
        "os",
        "para",
        "por",
        "que",
        "se",
        "ser",
        "sera",
        "será",
        "seu",
        "sua",
        "tem",
        "ter",
        "um",
        "uma",
        "vai",
        "vao",
        "vão",
    }
)

LIMITE_FALLBACK_INDICADORES = 10
LIMITE_PAIRS_CONTRADICAO = 200


def claim_from_evidencia(evidencia: Evidencia) -> ClaimData:
    """Converte uma ``Evidencia`` ORM em ``ClaimData`` (com ``fonte_url``).

    Args:
        evidencia: Evidência carregada (com relação ``fonte`` disponível).

    Returns:
        ClaimData com id, textos, fonte_url e tipo_claim.
    """
    return ClaimData(
        id=evidencia.id,
        titulo=evidencia.fonte.titulo if evidencia.fonte else None,
        resumo=evidencia.resumo,
        trecho=evidencia.trecho,
        fonte_url=evidencia.fonte.url if evidencia.fonte else None,
        tipo_claim=evidencia.tipo_claim.value if evidencia.tipo_claim else None,
    )


async def extract_indicators(
    texto: str,
    fonte_url: str | None = None,
    client: OllamaClient | None = None,
) -> ExtractionResult:
    """Extração assistida de indicadores com citação; fallback local se indisponível.

    Args:
        texto: Texto da fonte a analisar.
        fonte_url: URL da fonte (registrada na citação).
        client: Cliente Ollama injetado (testes). None usa configuração padrão.

    Returns:
        ExtractionResult com indicadores e citações — nunca falha.
    """
    texto = texto.strip()
    if not texto:
        logger.warning("extract_indicators: texto vazio — resultado vazio")
        return _resultado_vazio(fonte_url)
    llm = client or OllamaClient()
    prompt = build_extract_prompt(texto, fonte_url)
    result = await llm.generate_json(prompt, ExtractionResult, system=EXTRACT_INDICATORS_SYSTEM)
    if result is None:
        logger.warning("LLM indisponível/absteve — usando extração local determinística")
        return _fallback_extract_indicators(texto, fonte_url)
    return result.model_copy(
        update={
            "prompt_version": PROMPT_VERSION,
            "model_used": llm.model,
            "fonte_url": fonte_url or result.fonte_url,
        }
    )


def _resultado_vazio(fonte_url: str | None) -> ExtractionResult:
    """Resultado vazio (sem indicadores) para texto sem conteúdo."""
    return ExtractionResult(
        indicadores=[],
        fonte_url=fonte_url,
        prompt_version=PROMPT_VERSION,
        model_used="fallback-local",
    )


def _fallback_extract_indicators(texto: str, fonte_url: str | None) -> ExtractionResult:
    """Heurística determinística: extrai "número + unidade" com citação da sentença."""
    indicadores: list[ExtractedIndicator] = []
    vistos: set[str] = set()
    for m in _METRIC_RE.finditer(texto[:8000]):
        citacao = _contexto(texto, m.start())
        if citacao in vistos:
            continue
        vistos.add(citacao)
        indicadores.append(
            ExtractedIndicator(
                nome=_truncar(citacao, 120),
                valor=_float_from(m.group("valor")),
                unidade=_unidade_normalizada(m.group("unidade")),
                tipo="produto",
                trecho_citado=citacao,
                fonte_url=fonte_url,
            )
        )
        if len(indicadores) >= LIMITE_FALLBACK_INDICADORES:
            break
    if not indicadores:
        logger.info("Nenhum indicador detectado por heurística local")
    return ExtractionResult(
        indicadores=indicadores,
        fonte_url=fonte_url,
        prompt_version=PROMPT_VERSION,
        model_used="fallback-local",
    )


async def summarize_evidence(
    evidencia: ClaimData,
    client: OllamaClient | None = None,
) -> SummarizationResult | None:
    """Resumo assistido de uma evidência com citação obrigatória.

    Args:
        evidencia: Claim (ou evidência convertida) a resumir.
        client: Cliente Ollama injetado (testes). None usa configuração padrão.

    Returns:
        SummarizationResult com fonte e citação, ou ``None`` (abstention) se a
        evidência não tiver texto para citar.
    """
    texto = evidencia.texto
    if not texto:
        logger.warning(f"summarize_evidence: evidência {evidencia.id} sem texto — abstendo")
        return None
    llm = client or OllamaClient()
    prompt = build_summarize_prompt(evidencia.titulo or "", texto, evidencia.fonte_url)
    result = await llm.generate_json(prompt, SummarizationResult, system=SUMMARIZE_SYSTEM)
    if result is not None:
        return result.model_copy(
            update={
                "prompt_version": PROMPT_VERSION,
                "model_used": llm.model,
                "fonte_url": evidencia.fonte_url or result.fonte_url,
            }
        )
    logger.warning(f"LLM indisponível/absteve para {evidencia.id} — resumo local com citação")
    return _fallback_summarize(evidencia)


def _fallback_summarize(evidencia: ClaimData) -> SummarizationResult:
    """Resumo local determinístico: trecho truncado + citação da primeira frase."""
    texto = evidencia.trecho or evidencia.resumo or ""
    return SummarizationResult(
        resumo=_truncar(texto, 500),
        fonte_url=evidencia.fonte_url,
        trecho_citado=_primeira_frase(texto),
        prompt_version=PROMPT_VERSION,
        model_used="fallback-local",
    )


async def find_contradictions(
    evidencias: Sequence[ClaimData],
    client: OllamaClient | None = None,
    max_pairs: int = LIMITE_PAIRS_CONTRADICAO,
) -> list[ContradictionCandidate]:
    """Compara claims incompatíveis e retorna candidatos a contradição.

    Pares candidatos são gerados por heurística determinística (tipo_claim
    incompatível + mesmo tópico), sempre com trechos citados. Quando o LLM
    está disponível, cada par é refinado por julgamento; se o LLM afirmar que
    NÃO há contradição, o candidato é descartado. O LLM nunca altera status —
    retorna apenas candidatos para revisão humana.

    Args:
        evidencias: Claims a comparar (idealmente da mesma ação/meta).
        client: Cliente Ollama injetado (testes). None usa configuração padrão.
        max_pairs: Limite de pares avaliados no modo lote.

    Returns:
        Lista de ContradictionCandidate com trechos citados.
    """
    candidatos: list[ContradictionCandidate] = []
    pares = _pares_potenciais(evidencias)[:max_pairs]
    llm = client or OllamaClient()
    for ev_a, ev_b, razao_heuristica in pares:
        julgamento = await _julgar_contradicao(ev_a, ev_b, llm)
        if julgamento is not None and not julgamento.is_contradiction:
            continue
        candidatos.append(
            ContradictionCandidate(
                evidencia_a_id=ev_a.id,
                evidencia_b_id=ev_b.id,
                claim_a=_truncar(ev_a.texto, 500),
                claim_b=_truncar(ev_b.texto, 500),
                trecho_a=ev_a.trecho or _primeira_frase(ev_a.resumo or ev_a.texto),
                trecho_b=ev_b.trecho or _primeira_frase(ev_b.resumo or ev_b.texto),
                fonte_url_a=ev_a.fonte_url,
                fonte_url_b=ev_b.fonte_url,
                razao=julgamento.razao if julgamento else razao_heuristica,
                prompt_version=PROMPT_VERSION,
                model_used=llm.model if julgamento else "fallback-local",
            )
        )
    return candidatos


async def _julgar_contradicao(
    ev_a: ClaimData,
    ev_b: ClaimData,
    llm: OllamaClient,
) -> ContradictionJudgment | None:
    """Pede ao LLM um julgamento de contradição; ``None`` se abstiver."""
    prompt = build_contradiction_prompt(ev_a.texto, ev_a.tipo_claim, ev_b.texto, ev_b.tipo_claim)
    return await llm.generate_json(prompt, ContradictionJudgment, system=CONTRADICTION_SYSTEM)


def _pares_potenciais(
    evidencias: Sequence[ClaimData],
) -> list[tuple[ClaimData, ClaimData, str]]:
    """Gera pares potencialmente contraditórios (tipo incompatível + mesmo tópico)."""
    pares: list[tuple[ClaimData, ClaimData, str]] = []
    total = len(evidencias)
    for i in range(total):
        for j in range(i + 1, total):
            ev_a, ev_b = evidencias[i], evidencias[j]
            if not _claims_potencialmente_incompativeis(ev_a, ev_b):
                continue
            razao = _razao_heuristica(ev_a, ev_b)
            if razao is not None:
                pares.append((ev_a, ev_b, razao))
    return pares


def _claims_potencialmente_incompativeis(ev_a: ClaimData, ev_b: ClaimData) -> bool:
    """Indica se os tipos de claim sugerem incompatibilidade (promessa vs execução)."""
    if not ev_a.texto or not ev_b.texto:
        return False
    tipo_a = ev_a.tipo_claim or "observacao"
    tipo_b = ev_b.tipo_claim or "observacao"
    if tipo_a in _PROMESSA_TIPOS and tipo_b in _EXECUCAO_TIPOS:
        return True
    if tipo_b in _PROMESSA_TIPOS and tipo_a in _EXECUCAO_TIPOS:
        return True
    # Mesma natureza de execução pode se contradizer (ex.: entregue vs suspenso).
    return tipo_a in _EXECUCAO_TIPOS and tipo_a == tipo_b


def _razao_heuristica(ev_a: ClaimData, ev_b: ClaimData) -> str | None:
    """Justificativa heurística; ``None`` se as claims não compartilham tópico."""
    stems_a = {palavra[:5] for palavra in _palavras(ev_a.texto)}
    stems_b = {palavra[:5] for palavra in _palavras(ev_b.texto)}
    comuns = stems_a & stems_b
    if not comuns:
        return None
    tipo_a = ev_a.tipo_claim or "não classificado"
    tipo_b = ev_b.tipo_claim or "não classificado"
    return (
        f"Mesmo tópico ({', '.join(sorted(comuns)[:5])}) com claims de natureza "
        f"incompatível ({tipo_a} vs {tipo_b}) — candidato para revisão humana."
    )


def _palavras(texto: str) -> set[str]:
    """Palavras relevantes do texto (≥4 letras, sem stopwords)."""
    return {
        palavra
        for palavra in re.findall(r"[a-zà-ú]{4,}", texto.lower())
        if palavra not in _STOPWORDS
    }


def _contexto(texto: str, start: int) -> str:
    """Sentença/linha que contém a posição ``start`` (usada como citação)."""
    inicio = texto.rfind("\n", 0, start)
    if inicio == -1:
        inicio = texto.rfind(".", 0, start)
    if inicio == -1:
        inicio = 0
    else:
        inicio += 1  # pula o separador
    fim = texto.find("\n", start)
    if fim == -1:
        fim = texto.find(".", start)
    if fim == -1:
        fim = len(texto)
    sentenca = texto[inicio:fim].strip()
    if not sentenca:
        sentenca = texto[max(0, start - 80) : min(len(texto), start + 80)].strip()
    return sentenca


def _float_from(raw: str) -> float | None:
    """Converte número no formato brasileiro/estadunidense para float."""
    valor = raw.replace(".", "").replace(",", ".")
    try:
        return float(valor)
    except ValueError:
        return None


def _unidade_normalizada(raw: str) -> str | None:
    """Normaliza a unidade extraída (ex.: % -> percentual, bilhões -> bilhão)."""
    unidade = raw.strip().lower()
    if unidade == "%":
        return "percentual"
    if "bilh" in unidade:
        return "bilhão"
    if "milh" in unidade:
        return "milhão"
    return unidade


def _truncar(texto: str, limite: int) -> str:
    """Trunca texto com reticências se exceder o limite."""
    if len(texto) <= limite:
        return texto
    return texto[:limite].rstrip() + "…"


def _primeira_frase(texto: str) -> str:
    """Primeira frase/sentença de um texto (citação curta)."""
    for sep in (".", "\n", ";", "!", "?"):
        idx = texto.find(sep)
        if idx != -1:
            return texto[: idx + 1].strip()
    return texto.strip()
