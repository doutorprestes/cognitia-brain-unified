"""Pipeline de vinculação automática de evidências — IA Brasil.

Vincula evidências a ações do PBIA usando busca semântica (TF-IDF),
fuzzy matching e classificação por regras de domínio.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field

from loguru import logger
from sqlalchemy import select

from src.core.db import (
    Acao,
    EstadoVinculo,
    Evidencia,
    VinculoEvidencia,
    get_session,
)
from src.modules.linking.classifier import RelevanceClassifier
from src.modules.linking.matcher import TextMatcher

DEFAULT_CONFIDENCE_THRESHOLD = 0.7


@dataclass
class LinkSuggestion:
    """Sugestão de vínculo gerada pelo auto_linker."""

    evidencia_id: str
    acao_id: str
    confidence: float
    justification: str
    status: str  # relevante | parcial
    action_name: str = ""
    evidence_summary: str = ""


@dataclass
class AutoLinkResult:
    """Resultado completo da execução do auto_linker."""

    total_evidencias: int = 0
    evidencias_com_vinculo: int = 0
    evidencias_novas: int = 0
    vinculos_criados: int = 0
    suggestions: list[LinkSuggestion] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)


def _build_texto_evidencia(evidencia: Evidencia) -> str:
    """Constrói texto relevante da evidência para matching."""
    parts: list[str] = []
    if evidencia.resumo:
        parts.append(evidencia.resumo)
    if evidencia.trecho:
        parts.append(evidencia.trecho)
    return " ".join(parts).strip()


def _build_texto_acao(acao: Acao) -> str:
    """Constrói texto relevante da ação para matching."""
    parts: list[str] = []
    if acao.nome:
        parts.append(acao.nome)
    if acao.descricao:
        parts.append(acao.descricao)
    if acao.trecho_original:
        parts.append(acao.trecho_original)
    return " ".join(parts).strip()


def _processar_evidencia(
    evidencia: Evidencia,
    matcher: TextMatcher,
    classifier: RelevanceClassifier,
    acoes: list[Acao],
    confidence_threshold: float,
) -> tuple[list[LinkSuggestion], int]:
    """Processa uma evidência e retorna sugestões e vínculos criados."""
    suggestions: list[LinkSuggestion] = []
    vinculos = 0

    texto_ev = _build_texto_evidencia(evidencia)
    if not texto_ev:
        return suggestions, vinculos

    matches = matcher.match_evidence(evidencia.id, texto_ev, top_k=5)
    if not matches:
        return suggestions, vinculos

    textos = {evidencia.id: texto_ev}
    classifications = classifier.classify_batch(matches, textos)

    relevant = [
        c
        for c in classifications
        if c.confidence >= confidence_threshold and c.status in ("relevante", "parcial")
    ]

    # Mapear acoes por id para lookup rápido
    acoes_map = {a.id: a.nome for a in acoes}

    for classification in relevant:
        acao_nome = acoes_map.get(classification.acao_id, "")
        suggestions.append(
            LinkSuggestion(
                evidencia_id=evidencia.id,
                acao_id=classification.acao_id,
                confidence=classification.confidence,
                justification=classification.justification,
                status=classification.status,
                action_name=acao_nome,
                evidence_summary=evidencia.resumo or "",
            )
        )
        vinculos += 1

    return suggestions, vinculos


async def auto_link(
    confidence_threshold: float = DEFAULT_CONFIDENCE_THRESHOLD,
    dry_run: bool = False,
    limit: int | None = None,
) -> AutoLinkResult:
    """Executa o pipeline de vinculação automática.

    Args:
        confidence_threshold: Confiança mínima para criar vínculo (padrão: 0.7).
        dry_run: Se True, apenas sugere sem criar vínculos.
        limit: Limite de evidências a processar (None = todas).

    Returns:
        Resultado detalhado da execução.
    """
    result = AutoLinkResult()

    async with get_session() as session:
        # 1. Buscar dados
        acoes = list((await session.execute(select(Acao))).scalars())
        if not acoes:
            logger.warning("Nenhuma ação encontrada no banco")
            return result

        ev_query = select(Evidencia)
        if limit:
            ev_query = ev_query.limit(limit)
        evidencias = list((await session.execute(ev_query)).scalars())
        result.total_evidencias = len(evidencias)

        if not evidencias:
            logger.warning("Nenhuma evidência encontrada no banco")
            return result

        # 2. Identificar evidências sem vínculo
        vinculos_result = await session.execute(select(VinculoEvidencia.evidencia_id))
        ev_ids_com_vinculo = {row[0] for row in vinculos_result}
        result.evidencias_com_vinculo = len(ev_ids_com_vinculo)

        evidencias_sem_vinculo = [ev for ev in evidencias if ev.id not in ev_ids_com_vinculo]
        result.evidencias_novas = len(evidencias_sem_vinculo)

        if not evidencias_sem_vinculo:
            logger.info("Todas as evidências já possuem vínculos")
            return result

        # 3. Preparar matcher e classificador
        matcher = TextMatcher()
        matcher.fit_acoes(
            [
                {
                    "id": a.id,
                    "nome": a.nome,
                    "descricao": a.descricao,
                    "trecho_original": a.trecho_original,
                }
                for a in acoes
            ]
        )
        classifier = RelevanceClassifier()

        # 4. Processar cada evidência
        for evidencia in evidencias_sem_vinculo:
            try:
                suggestions, vinculos = _processar_evidencia(
                    evidencia, matcher, classifier, acoes, confidence_threshold
                )
                result.suggestions.extend(suggestions)

                if not dry_run and vinculos > 0:
                    for sug in suggestions:
                        vinculo = VinculoEvidencia(
                            id=str(uuid.uuid4()),
                            evidencia_id=sug.evidencia_id,
                            acao_id=sug.acao_id,
                            justificativa=(
                                f"[Auto-link] {sug.justification} (confiança: {sug.confidence:.3f})"
                            ),
                            criado_por="auto_linker",
                            # Vínculos automáticos entram como proposto e dependem
                            # de revisão humana no admin (issue #1098) — nunca aprovado.
                            estado=EstadoVinculo.proposto,
                        )
                        session.add(vinculo)
                    result.vinculos_criados += vinculos
                    logger.info(f"Vínculos criados: {evidencia.id} → {len(suggestions)} ações")
            except Exception as e:
                error_msg = f"Erro ao processar evidência {evidencia.id}: {e}"
                logger.error(error_msg)
                result.errors.append(error_msg)

        if not dry_run and result.vinculos_criados > 0:
            await session.flush()

    logger.info(
        f"Auto-link concluído: {result.vinculos_criados} vínculos criados, "
        f"{len(result.suggestions)} sugestões, {len(result.errors)} erros"
    )
    return result


async def get_stats() -> dict[str, int | dict[str, int]]:
    """Retorna estatísticas de vinculação.

    Returns:
        Dict com total, por método, por status.
    """
    async with get_session() as session:
        from sqlalchemy import func

        # Total
        result = await session.execute(select(func.count()).select_from(VinculoEvidencia))
        total = result.scalar() or 0

        # Por criado_por
        result = await session.execute(
            select(VinculoEvidencia.criado_por, func.count(VinculoEvidencia.id)).group_by(
                VinculoEvidencia.criado_por
            )
        )
        por_metodo = {str(row[0] or "desconhecido"): row[1] for row in result}

        # Evidências sem vínculo
        result = await session.execute(select(func.count()).select_from(Evidencia))
        total_evidencias = result.scalar() or 0

        result = await session.execute(select(VinculoEvidencia.evidencia_id).distinct())
        ev_com_vinculo = len(list(result))

        return {
            "total_vinculos": total,
            "por_metodo": por_metodo,
            "total_evidencias": total_evidencias,
            "evidencias_com_vinculo": ev_com_vinculo,
            "evidencias_sem_vinculo": total_evidencias - ev_com_vinculo,
        }
