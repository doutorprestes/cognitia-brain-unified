"""Pipeline de auditoria — IA Brasil.

Registra trilha imutável de mudanças de status de ações.
Cada avaliação do scoring pipeline gera um registro de auditoria
com diff do status anterior, justificativa e metadados.

Uso:
    pipeline = AuditPipeline()
    history = await pipeline.get_history("acao_id")
    diff = await pipeline.get_last_diff("acao_id")
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import desc, select

from src.core.db import (
    AuditLog,
    StatusAcao,
    get_session,
)


@dataclass
class AuditDiff:
    """Diferença entre dois status consecutivos."""

    status_anterior: StatusAcao | None
    status_novo: StatusAcao
    data_mudanca: str
    justificativa: str
    criado_por: str
    versao: int


@dataclass
class AuditHistory:
    """Histórico completo de mudanças de status de uma ação."""

    acao_id: str
    total_mudancas: int
    mudancas: list[AuditDiff] = field(default_factory=list)


class AuditPipeline:
    """Pipeline para consulta de histórico de auditoria de ações."""

    @staticmethod
    async def get_history(acao_id: str) -> AuditHistory:
        """Retorna histórico completo de mudanças de status.

        Args:
            acao_id: ID da ação.

        Returns:
            AuditHistory com todas as mudanças ordenadas por data.
        """
        async with get_session() as session:
            result = await session.execute(
                select(AuditLog)
                .where(AuditLog.acao_id == acao_id)
                .order_by(desc(AuditLog.data_criacao), desc(AuditLog.id))
            )
            logs = list(result.scalars())

            mudancas = []
            for i, log in enumerate(logs):
                mudancas.append(
                    AuditDiff(
                        status_anterior=log.status_anterior,
                        status_novo=log.status_novo,
                        data_mudanca=log.data_criacao.isoformat(),
                        justificativa=log.justificativa,
                        criado_por=log.criado_por,
                        versao=len(logs) - i,
                    )
                )

            return AuditHistory(
                acao_id=acao_id,
                total_mudancas=len(mudancas),
                mudancas=mudancas,
            )

    @staticmethod
    async def get_last_diff(acao_id: str) -> AuditDiff | None:
        """Retorna a última mudança de status de uma ação.

        Args:
            acao_id: ID da ação.

        Returns:
            AuditDiff da última mudança ou None se não houver registros.
        """
        async with get_session() as session:
            result = await session.execute(
                select(AuditLog)
                .where(AuditLog.acao_id == acao_id)
                .order_by(desc(AuditLog.data_criacao), desc(AuditLog.id))
                .limit(1)
            )
            log = result.scalar_one_or_none()

            if not log:
                return None

            return AuditDiff(
                status_anterior=log.status_anterior,
                status_novo=log.status_novo,
                data_mudanca=log.data_criacao.isoformat(),
                justificativa=log.justificativa,
                criado_por=log.criado_por,
                versao=1,
            )

    @staticmethod
    async def get_all_audit_logs(
        limit: int = 100,
        offset: int = 0,
    ) -> list[dict[str, Any]]:
        """Retorna logs de auditoria paginados.

        Args:
            limit: Limite de registros.
            offset: Offset para paginação.

        Returns:
            Lista de dicts com dados dos logs.
        """
        async with get_session() as session:
            result = await session.execute(
                select(AuditLog).order_by(desc(AuditLog.data_criacao)).offset(offset).limit(limit)
            )
            logs = list(result.scalars())

            return [
                {
                    "id": log.id,
                    "acao_id": log.acao_id,
                    "status_anterior": (log.status_anterior.value if log.status_anterior else None),
                    "status_novo": log.status_novo.value,
                    "justificativa": log.justificativa,
                    "criado_por": log.criado_por,
                    "data_criacao": log.data_criacao.isoformat(),
                }
                for log in logs
            ]
