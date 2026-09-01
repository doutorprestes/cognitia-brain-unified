"""Schemas Pydantic para ingestão de evidências.

Estende os schemas básicos do db.py com validações específicas para ingestão.
"""

from datetime import date
from typing import Any

from pydantic import BaseModel, Field, HttpUrl, field_validator

from src.core.db import (
    AvaliacaoCreate,
    EventoCreate,
    EvidenciaCreate,
    FonteCreate,
    TipoEvento,
    TipoEvidencia,
    VinculoCreate,
)

# ---------------------------------------------------------------------------
# Fonte
# ---------------------------------------------------------------------------


class FonteCreateExtended(FonteCreate):
    """Schema estendido para criação de Fonte com validações adicionais."""

    url: HttpUrl = Field(..., description="URL válida da fonte primária")  # type: ignore[assignment]
    data_coleta: date = Field(
        default_factory=date.today, description="Data de coleta (default: hoje)"
    )


class FonteReadExtended(FonteCreateExtended):
    """Schema para leitura de Fonte."""

    id: str


# ---------------------------------------------------------------------------
# Evidência
# ---------------------------------------------------------------------------


class EvidenciaCreateExtended(EvidenciaCreate):
    """Schema estendido para criação de Evidência com validações adicionais."""

    tipo: TipoEvidencia
    confianca: float | None = Field(
        default=None, ge=0.0, le=1.0, description="Nível de confiança (0.0-1.0)"
    )

    @field_validator("confianca", mode="before")
    @classmethod
    def validate_confianca(cls, v: float | None) -> float | None:
        """Valida que confiança está entre 0.0 e 1.0."""
        if v is None:
            return None
        if not 0.0 <= v <= 1.0:
            raise ValueError("confianca deve estar entre 0.0 e 1.0")
        return v


class EvidenciaReadExtended(EvidenciaCreate):
    """Schema para leitura de Evidência com fonte aninhada."""

    id: str
    fonte: FonteReadExtended | None = None


# ---------------------------------------------------------------------------
# Vínculo
# ---------------------------------------------------------------------------


class VinculoCreateExtended(VinculoCreate):
    """Schema estendido para criação de Vínculo."""

    justificativa: str | None = Field(
        default=None, min_length=10, description="Justificativa mínima de 10 caracteres"
    )


class VinculoReadExtended(VinculoCreateExtended):
    """Schema para leitura de Vínculo com evidência e ação aninhadas."""

    id: str
    evidencia: EvidenciaReadExtended | None = None
    acao: dict[str, Any] | None = None  # AcaoRead será importado circularmente


# ---------------------------------------------------------------------------
# Avaliação
# ---------------------------------------------------------------------------


class AvaliacaoCreateExtended(AvaliacaoCreate):
    """Schema estendido para criação de Avaliação."""

    justificativa: str = Field(
        ..., min_length=20, description="Justificativa mínima de 20 caracteres"
    )


class AvaliacaoReadExtended(AvaliacaoCreateExtended):
    """Schema para leitura de Avaliação com ação aninhada."""

    acao: dict[str, Any] | None = None  # AcaoRead será importado circularmente


# ---------------------------------------------------------------------------
# Evento
# ---------------------------------------------------------------------------


class EventoCreateExtended(EventoCreate):
    """Schema estendido para criação de Evento."""

    tipo: "TipoEvento"
    descricao: str = Field(..., min_length=10, description="Descrição mínima de 10 caracteres")
    data_evento: date = Field(..., description="Data do evento")
    fonte_url: HttpUrl | None = Field(default=None, description="URL da fonte do evento")  # type: ignore[assignment]


class EventoReadExtended(EventoCreateExtended):
    """Schema para leitura de Evento."""

    id: str
    acao: dict[str, Any] | None = None


# ---------------------------------------------------------------------------
# Schemas de resposta para listagem
# ---------------------------------------------------------------------------


class EvidenciaListItem(EvidenciaReadExtended):
    """Item de evidência para listagem paginada."""

    pass


class EvidenciaListResponse(BaseModel):
    """Resposta paginada de evidências."""

    items: list[EvidenciaListItem]
    total: int
    page: int
    page_size: int
    total_pages: int
