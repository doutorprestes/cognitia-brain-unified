"""Classificador de relevância evidência-ação — IA Brasil.

Combina regras de domínio com similaridade textual para classificar
pares evidência-ação como relevante, parcial ou irrelevante.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from loguru import logger

if TYPE_CHECKING:
    from src.modules.linking.matcher import MatchResult

# ── Thresholds ──────────────────────────────────────────────────────────

RELEVANT_THRESHOLD = 0.7
PARTIAL_THRESHOLD = 0.4

# ── Termos de alta evidência ───────────────────────────────────────────

_HIGH_EVIDENCE_TERMS: set[str] = {
    "contrato",
    "licitação",
    "edital",
    "portaria",
    "decreto",
    "lei",
    "resolução",
    "at",
    "despacho",
    "diário oficial",
    "dou",
    "publicação",
    "resultado",
    "relatório",
    "prestação de contas",
}


@dataclass
class Classification:
    """Resultado da classificação de um par evidência-ação."""

    evidencia_id: str
    acao_id: str
    status: str  # relevante | parcial | irrelevante
    confidence: float
    justification: str
    match_result: MatchResult


class RelevanceClassifier:
    """Classifica relevância entre evidência e ação do PBIA."""

    def __init__(
        self,
        relevant_threshold: float = RELEVANT_THRESHOLD,
        partial_threshold: float = PARTIAL_THRESHOLD,
    ) -> None:
        self._relevant_threshold = relevant_threshold
        self._partial_threshold = partial_threshold

    def _compute_confidence(
        self,
        match: MatchResult,
        texto_evidencia: str,
    ) -> tuple[float, str]:
        """Calcula confiança e justificativa para o par evidência-ação.

        Fatores:
        1. Score combinado do matcher (peso principal)
        2. Presença de termos de alta evidência
        3. Quantidade de keywords matching

        Returns:
            Tupla (confiança, justificativa).
        """
        base_score = match.combined_score

        # Boost por termos de alta evidência
        ev_lower = texto_evidencia.lower()
        high_evidence_hits = [t for t in _HIGH_EVIDENCE_TERMS if t in ev_lower]
        evidence_boost = min(len(high_evidence_hits) * 0.05, 0.15)

        # Boost por keywords matching
        keyword_boost = min(len(match.matching_keywords) * 0.02, 0.10)

        confidence = min(base_score + evidence_boost + keyword_boost, 1.0)

        # Justificativa
        parts: list[str] = []
        parts.append(f"Score combinado: {base_score:.3f}")
        if high_evidence_hits:
            parts.append(f"Termos de alta evidência: {', '.join(high_evidence_hits[:3])}")
        if match.matching_keywords:
            parts.append(f"Keywords PBIA: {', '.join(match.matching_keywords[:5])}")
        if match.tfidf_score > 0.5:
            parts.append(f"Alta similaridade TF-IDF ({match.tfidf_score:.3f})")
        if match.fuzzy_score > 0.6:
            parts.append(f"Alta similaridade textual ({match.fuzzy_score:.3f})")

        justification = "; ".join(parts) if parts else "Sem sinais fortes"

        return confidence, justification

    def classify(
        self,
        match: MatchResult,
        texto_evidencia: str,
    ) -> Classification:
        """Classifica um par evidência-ação.

        Args:
            match: Resultado do matcher para o par.
            texto_evidencia: Texto da evidência para análise adicional.

        Returns:
            Classificação com status, confiança e justificativa.
        """
        confidence, justification = self._compute_confidence(match, texto_evidencia)

        if confidence >= self._relevant_threshold:
            status = "relevante"
        elif confidence >= self._partial_threshold:
            status = "parcial"
        else:
            status = "irrelevante"

        logger.debug(
            f"Classificação: evid={match.evidencia_id} acao={match.acao_id} "
            f"→ {status} ({confidence:.3f})"
        )

        return Classification(
            evidencia_id=match.evidencia_id,
            acao_id=match.acao_id,
            status=status,
            confidence=confidence,
            justification=justification,
            match_result=match,
        )

    def classify_batch(
        self,
        matches: list[MatchResult],
        textos_evidencias: dict[str, str],
    ) -> list[Classification]:
        """Classifica um lote de matches.

        Args:
            matches: Lista de resultados do matcher.
            textos_evidencias: Dict mapeando evidencia_id → texto relevante.

        Returns:
            Lista de classificações ordenadas por confiança decrescente.
        """
        classifications: list[Classification] = []

        for match in matches:
            texto = textos_evidencias.get(match.evidencia_id, "")
            if not texto:
                logger.warning(f"Texto não encontrado para evidência {match.evidencia_id}")
                continue

            classification = self.classify(match, texto)
            classifications.append(classification)

        classifications.sort(key=lambda c: c.confidence, reverse=True)
        return classifications

    def filter_relevant(
        self,
        classifications: list[Classification],
        min_confidence: float | None = None,
    ) -> list[Classification]:
        """Filtra classificações mantendo apenas relevantes/parciais.

        Args:
            classifications: Lista de classificações.
            min_confidence: Confiança mínima (padrão: threshold de parcial).

        Returns:
            Lista filtrada e ordenada.
        """
        threshold = min_confidence if min_confidence is not None else self._partial_threshold
        return [
            c for c in classifications if c.confidence >= threshold and c.status != "irrelevante"
        ]
