"""Schemas para qualidade de dados — IA Brasil."""

from __future__ import annotations

from datetime import date, datetime  # noqa: TC003
from enum import StrEnum

from pydantic import BaseModel, Field


class ValidationSeverity(StrEnum):
    """Severidade de uma violação de validação."""

    ERROR = "error"
    WARNING = "warning"
    INFO = "info"


class ValidationViolation(BaseModel):
    """Uma única violação encontrada durante validação."""

    rule: str = Field(..., description="Identificador da regra violada")
    severity: ValidationSeverity
    entity: str = Field(..., description="Entidade afetada (ex: acoes, metas)")
    entity_id: str | None = Field(None, description="ID da entidade afetada")
    message: str = Field(..., description="Descrição da violação")
    details: dict[str, object] | None = Field(None, description="Detalhes adicionais da violação")


class ValidationResult(BaseModel):
    """Resultado completo de uma execução de validação."""

    ran_at: datetime
    total_violations: int
    errors: int
    warnings: int
    info: int
    violations: list[ValidationViolation]
    summary: dict[str, object]


class DataFreshnessInfo(BaseModel):
    """Informação de frescor de uma fonte de dados."""

    source: str
    last_collection: date | None
    days_since_collection: int | None
    total_runs: int
    consecutive_failures: int
    status: str = Field(..., description="healthy, stale, ou critical")
    periodicidade: str | None = Field(
        None, description="Cadência declarada da fonte: '2x/ano' ou 'manual' (issue #1103)"
    )
    ultima_referencia: date | None = Field(
        None, description="Data do documento oficial mais recente (ex.: relatório CGEE)"
    )


class DataQualityMetrics(BaseModel):
    """Métricas agregadas de qualidade dos dados."""

    total_planos: int
    total_eixos: int
    total_programas: int
    total_acoes: int
    total_metas: int
    total_indicadores: int
    total_recursos: int
    total_evidencias: int
    total_vinculos: int
    acoes_por_status: dict[str, int]
    acoes_sem_status: int = Field(..., description="Ações com status nao_iniciado")
    total_valor_previsto: float | None = Field(None, description="Soma dos valores previstos (R$)")
    freshness: list[DataFreshnessInfo]
    referential_integrity_violations: int
    schema_violations: int


class HealthDataFreshnessResponse(BaseModel):
    """Resposta do endpoint de health de frescor dos dados."""

    status: str = Field(..., description="healthy, degraded, ou critical")
    checked_at: datetime
    freshness: list[DataFreshnessInfo]
    overall_days_since_latest: int | None
    details: str


class VolumeCheck(BaseModel):
    """Check de volume de itens coletados por fonte."""

    items_fetched: int = Field(..., description="Itens do último run terminal")
    previous_items: int | None = Field(None, description="Itens do último run de sucesso anterior")
    delta_pct: float | None = Field(None, description="Variação percentual vs último sucesso")
    status: str = Field(..., description="healthy, degraded, ou critical")


class FreshnessCheck(BaseModel):
    """Check de frescor de uma fonte (severidade normalizada)."""

    last_collection: date | None
    days_since_collection: int | None
    consecutive_failures: int
    status: str = Field(..., description="healthy, degraded, ou critical")


class SchemaDriftCheck(BaseModel):
    """Check de drift de schema via mudança de parser_version."""

    parser_version: str | None = Field(None, description="parser_version do último run terminal")
    previous_parser_version: str | None = Field(
        None, description="parser_version do run terminal anterior"
    )
    drift_detected: bool = Field(..., description="True se a parser_version mudou")
    status: str = Field(..., description="healthy ou degraded quando drift detectado")


class QuarantineCheck(BaseModel):
    """Check de quarentena: runs partial recentes."""

    recent_partial_runs: int = Field(..., description="Runs partial nos últimos N dias")
    last_quarantine_reason: str | None = Field(
        None, description="Motivo do último run em quarentena"
    )
    status: str = Field(..., description="healthy, degraded, ou critical")


class SourceQualityChecks(BaseModel):
    """Checks de qualidade agregados por fonte."""

    source: str
    volume: VolumeCheck
    freshness: FreshnessCheck
    schema_drift: SchemaDriftCheck
    quarantine: QuarantineCheck


class DatasetQualityScore(BaseModel):
    """Score 0-100 de qualidade de um dataset/fonte."""

    source: str
    score: int = Field(..., ge=0, le=100, description="Score combinado de qualidade")
    severity: str = Field(..., description="healthy, degraded, ou critical")
    checks: SourceQualityChecks


class QualityReportResponse(BaseModel):
    """Relatório público de qualidade dos dados (score por fonte + checks)."""

    generated_at: datetime
    overall_score: int = Field(..., ge=0, le=100)
    overall_severity: str = Field(..., description="healthy, degraded, ou critical")
    datasets: list[DatasetQualityScore]


class QualityAlert(BaseModel):
    """Alerta ativo de qualidade de dados."""

    id: str
    severity: str = Field(..., description="degraded ou critical")
    category: str = Field(..., description="freshness, volume, schema_drift, ou quarantine")
    source: str | None = Field(None, description="Fonte afetada (None para alerta global)")
    message: str
    created_at: datetime
