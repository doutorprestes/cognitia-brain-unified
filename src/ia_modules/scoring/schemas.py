"""Schemas Pydantic para cálculo de status (scoring)."""

from datetime import date
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field


class EvidenceWeight(StrEnum):
    """Peso de uma evidência no cálculo de status."""

    PRIMARY = "primary"  # Fonte oficial (MCTI, CGEE, etc.)
    SECONDARY = "secondary"  # Notícias institucionais
    TERTIARY = "tertiary"  # Notícias de terceiros


class ScoringRule(BaseModel):
    """Regra de cálculo de status."""

    name: str
    description: str
    condition: str  # Descrição da condição em linguagem natural
    weight: float = 1.0


class StatusCalculation(BaseModel):
    """Resultado do cálculo de status para uma ação."""

    acao_id: str
    current_status: str
    proposed_status: str
    confidence: float = Field(ge=0.0, le=1.0, description="Confiança no status (0.0-1.0)")
    rules_applied: list[str] = Field(default_factory=list)
    justification: str = Field(..., min_length=10, description="Justificativa detalhada")
    evidence_count: int = 0
    latest_evidence_date: date | None = None


class ScoringRequest(BaseModel):
    """Requisição para cálculo de status."""

    acao_id: str = Field(..., description="ID da ação a ser avaliada")
    force_recalculate: bool = Field(
        default=False, description="Forçar recálculo mesmo com avaliação existente"
    )


class ScoringResult(BaseModel):
    """Resultado completo do scoring."""

    acao_id: str
    status: str
    calculation: StatusCalculation
    supporting_evidence: list[dict[str, Any]] = Field(default_factory=list)
    conflicting_evidence: list[dict[str, Any]] = Field(default_factory=list)


class BulkScoringRequest(BaseModel):
    """Requisição para cálculo em lote."""

    acao_ids: list[str] | None = Field(
        default=None, description="IDs específicas de ações a avaliar"
    )
    eixo_id: str | None = Field(default=None, description="Filtrar por eixo")
    programa_id: str | None = Field(default=None, description="Filtrar por programa")


class BulkScoringResult(BaseModel):
    """Resultado de scoring em lote."""

    results: list[ScoringResult] = Field(default_factory=list)
    total: int = 0
    processed: int = 0
    failed: int = 0
