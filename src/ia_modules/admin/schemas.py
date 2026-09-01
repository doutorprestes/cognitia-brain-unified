"""Schemas Pydantic para o módulo admin — IA Brasil.

Define schemas para operações administrativas: evidências,
vínculos, avaliações e dashboard.
"""

from datetime import date, datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, computed_field

from src.core.db import (
    AvaliacaoCreate,
    EstadoVinculo,
    EvidenciaCreate,
    StatusAcao,
    TipoEvidencia,
    VinculoCreate,
)

# ---------------------------------------------------------------------------
# Evidências — Admin
# ---------------------------------------------------------------------------


class AdminEvidenciaFilter(BaseModel):
    """Filtros para listagem de evidências no admin."""

    fonte_id: str | None = None
    tipo: TipoEvidencia | None = None
    data_inicio: date | None = None
    data_fim: date | None = None
    confianca_min: float | None = None
    confianca_max: float | None = None
    limit: int = Field(default=50, ge=1, le=200)
    offset: int = Field(default=0, ge=0)


class AdminEvidenciaCreate(EvidenciaCreate):
    """Schema para criação de evidência no admin."""

    confianca: float | None = Field(default=None, ge=0.0, le=1.0)


class AdminEvidenciaUpdate(BaseModel):
    """Schema para atualização de evidência no admin."""

    model_config = ConfigDict(extra="forbid")

    tipo: TipoEvidencia | None = None
    trecho: str | None = None
    resumo: str | None = None
    data_evidencia: date | None = None
    confianca: float | None = Field(default=None, ge=0.0, le=1.0)


class AdminEvidenciaRead(BaseModel):
    """Schema para leitura de evidência no admin."""

    id: str
    fonte_id: str
    tipo: TipoEvidencia
    trecho: str | None = None
    resumo: str | None = None
    data_evidencia: date | None = None
    confianca: float | None = None
    fonte_url: str | None = None
    fonte_titulo: str | None = None


# ---------------------------------------------------------------------------
# Vínculos — Admin
# ---------------------------------------------------------------------------


class AdminVinculoFilter(BaseModel):
    """Filtros para listagem de vínculos no admin."""

    acao_id: str | None = None
    evidencia_id: str | None = None
    criado_por: str | None = None
    estado: EstadoVinculo | None = None
    limit: int = Field(default=50, ge=1, le=200)
    offset: int = Field(default=0, ge=0)


class AdminVinculoCreate(VinculoCreate):
    """Schema para criação de vínculo no admin."""

    justificativa: str = Field(..., min_length=10, max_length=2000)
    criado_por: str = Field(default="admin")


class AdminVinculoApprove(BaseModel):
    """Schema para aprovação/rejeição de vínculo."""

    aprovado: bool
    justificativa: str | None = Field(default=None, max_length=2000)


class AdminVinculoRead(BaseModel):
    """Schema para leitura de vínculo no admin."""

    id: str
    evidencia_id: str
    acao_id: str
    meta_id: str | None = None
    justificativa: str | None = None
    criado_por: str | None = None
    aprovado_por: str | None = None
    estado: EstadoVinculo = EstadoVinculo.proposto
    revisor: str | None = None
    metodo: str | None = None
    score: float | None = None
    revisado_em: datetime | None = None
    evidencia_resumo: str | None = None
    acao_nome: str | None = None


# ---------------------------------------------------------------------------
# Avaliações — Admin
# ---------------------------------------------------------------------------


class AdminAvaliacaoFilter(BaseModel):
    """Filtros para listagem de avaliações no admin."""

    acao_id: str | None = None
    status: StatusAcao | None = None
    avaliado_por: str | None = None
    limit: int = Field(default=50, ge=1, le=200)
    offset: int = Field(default=0, ge=0)


class AdminAvaliacaoCreate(AvaliacaoCreate):
    """Schema para criação de avaliação no admin."""

    justificativa: str = Field(..., min_length=20, max_length=5000)


class AdminAvaliacaoUpdate(BaseModel):
    """Schema para atualização de avaliação no admin."""

    model_config = ConfigDict(extra="forbid")

    status_avaliado: StatusAcao | None = None
    justificativa: str | None = Field(default=None, min_length=20, max_length=5000)


class AdminAvaliacaoRead(BaseModel):
    """Schema para leitura de avaliação no admin."""

    id: str
    acao_id: str
    status_avaliado: StatusAcao
    justificativa: str
    avaliado_por: str | None = None
    data_avaliacao: date
    versao: int
    evidencias_usadas: list[dict[str, Any]] = []
    acao_nome: str | None = None


class AdminAvaliacaoHistory(BaseModel):
    """Histórico de alterações de uma avaliação."""

    avaliacao_id: str
    acao_id: str
    alteracoes: list[AdminAvaliacaoRead]


# ---------------------------------------------------------------------------
# Eventos — Admin
# ---------------------------------------------------------------------------


class AdminEventoFilter(BaseModel):
    """Filtros para listagem de eventos no admin."""

    acao_id: str | None = None
    tipo: str | None = None
    limit: int = Field(default=50, ge=1, le=200)
    offset: int = Field(default=0, ge=0)


class AdminEventoRead(BaseModel):
    """Schema para leitura de evento no admin."""

    id: str
    acao_id: str
    tipo: str
    descricao: str
    data_evento: date
    fonte_url: str | None = None
    acao_nome: str | None = None


# ---------------------------------------------------------------------------
# Dashboard — Admin
# ---------------------------------------------------------------------------


class AdminDashboardMetrics(BaseModel):
    """Métricas do dashboard admin."""

    total_acoes: int
    acoes_com_status: int
    acoes_sem_status: int
    total_evidencias: int
    evidencias_pendentes: int
    total_vinculos: int
    vinculos_pendentes: int
    total_avaliacoes: int
    acoes_por_status: dict[str, int]
    evidencias_por_tipo: dict[str, int]


class AdminIngestionStatus(BaseModel):
    """Status de uma execução de ingestão."""

    id: str
    source: str
    started_at: datetime
    finished_at: datetime | None = None
    status: str
    items_fetched: int
    items_new: int
    items_updated: int
    error_message: str | None = None

    @computed_field  # type: ignore[prop-decorator]
    @property
    def duration_minutes(self) -> float | None:
        """Retorna a duração da ingestão em minutos."""
        if self.finished_at is None:
            return None
        delta = self.finished_at - self.started_at
        return delta.total_seconds() / 60


class AdminQualityAlert(BaseModel):
    """Alerta de qualidade."""

    tipo: str
    descricao: str
    entidade_id: str | None = None
    entidade_tipo: str | None = None
    severidade: str  # info, warning, error


class AdminDashboard(BaseModel):
    """Dashboard admin completo."""

    metrics: AdminDashboardMetrics
    ultimas_coletas: list[AdminIngestionStatus]
    alertas: list[AdminQualityAlert]


# ---------------------------------------------------------------------------
# Resposta paginada genérica
# ---------------------------------------------------------------------------


class AdminPaginatedResponse(BaseModel):
    """Resposta paginada genérica."""

    items: list[dict[str, Any]]
    total: int
    page: int
    page_size: int
    total_pages: int
