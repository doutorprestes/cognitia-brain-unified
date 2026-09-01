"""Schemas Pydantic para o módulo de auditoria — IA Brasil.

Schemas de entrada/saída para o serviço de auditoria.
"""

from datetime import date
from typing import Any

from pydantic import BaseModel, Field

from src.core.db import StatusAcao


class AuditLogCreate(BaseModel):
    """Schema para criação de registro de auditoria."""

    id: str
    acao_id: str
    status_anterior: StatusAcao | None = None
    status_novo: StatusAcao
    justificativa: str
    criado_por: str
    data_criacao: date
    extra_data: dict[str, Any] = Field(default_factory=dict)


class AuditLogRead(AuditLogCreate):
    """Schema para leitura de registro de auditoria."""

    pass


class AuditHistoryRequest(BaseModel):
    """Filtros para consulta de histórico de auditoria."""

    acao_id: str | None = None
    status_anterior: StatusAcao | None = None
    status_novo: StatusAcao | None = None
    criado_por: str | None = None
    data_inicio: date | None = None
    data_fim: date | None = None
    limit: int = 100


class AuditHistoryResult(BaseModel):
    """Resultado da consulta de histórico de auditoria."""

    audit_logs: list[AuditLogRead]
    total: int


class AuditDiffRead(BaseModel):
    """Schema para leitura de diff de auditoria."""

    status_anterior: StatusAcao | None = None
    status_novo: StatusAcao
    data_mudanca: str
    justificativa: str
    criado_por: str
    versao: int


class AuditHistoryResponse(BaseModel):
    """Schema para resposta do histórico completo de auditoria."""

    acao_id: str
    total_mudancas: int
    mudancas: list[AuditDiffRead]
