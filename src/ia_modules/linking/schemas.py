"""Schemas Pydantic para vinculação de evidências."""

from typing import Any

from pydantic import BaseModel, Field

from src.core.db import VinculoCreate


class LinkCreate(VinculoCreate):
    """Schema para criação de vínculo entre evidência e ação/meta."""

    justificativa: str = Field(
        ...,
        min_length=20,
        max_length=2000,
        description="Justificativa detalhada da vinculação (20-2000 caracteres)",
    )
    criado_por: str = Field(
        default="manual",
        description="Origem da vinculação: 'manual', 'automatico', 'revisado'",
    )


class LinkRead(LinkCreate):
    """Schema para leitura de vínculo com detalhes."""

    id: str


class LinkSearch(BaseModel):
    """Schema para busca de vínculos."""

    evidencia_id: str | None = None
    acao_id: str | None = None
    meta_id: str | None = None
    criado_por: str | None = None
    limit: int = 100
    offset: int = 0


class LinkWithDetails(LinkRead):
    """Schema para vínculo com detalhes da evidência e ação."""

    evidencia: dict[str, Any] | None = None
    acao: dict[str, Any] | None = None
    meta: dict[str, Any] | None = None
