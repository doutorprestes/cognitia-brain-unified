"""Gerador de relatório de status — IA Brasil.

Gera relatórios agregados de status das ações do PBIA,
incluindo dashboards por eixo e estatísticas gerais.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import desc, func, or_, select
from sqlalchemy.orm import joinedload

from src.core.db import (
    Acao,
    AuditLog,
    Avaliacao,
    Eixo,
    EstadoVinculo,
    Evidencia,
    Programa,
    StatusAcao,
    VinculoEvidencia,
    get_session,
)
from src.core.pii import log_evidence_access, redact_pii


@dataclass
class StatusCount:
    """Contagem de ações por status."""

    status: StatusAcao
    count: int
    percentage: float


@dataclass
class EixoDashboard:
    """Dashboard de status para um eixo."""

    eixo_id: str
    eixo_nome: str
    total_acoes: int
    status_counts: list[StatusCount] = field(default_factory=list)
    progresso_entregue: float = 0.0
    progresso_andamento: float = 0.0


@dataclass
class GlobalDashboard:
    """Dashboard global de status."""

    total_acoes: int
    status_counts: list[StatusCount] = field(default_factory=list)
    eixos: list[EixoDashboard] = field(default_factory=list)
    progresso_geral: float = 0.0


class ScoringReport:
    """Gerador de relatórios de status."""

    @staticmethod
    async def get_acao_status(acao_id: str) -> dict[str, Any]:
        """Retorna status calculado + justificativa + evidências de uma ação.

        Args:
            acao_id: ID da ação.

        Returns:
            Dict com status, justificativa, evidências e histórico.

        Raises:
            ValueError: Se a ação não for encontrada.
        """
        async with get_session() as session:
            acao_result = await session.execute(select(Acao).where(Acao.id == acao_id))
            acao = acao_result.scalar_one_or_none()
            if not acao:
                raise ValueError(f"Ação não encontrada: {acao_id}")

            # Buscar evidências vinculadas (apenas vínculos aprovados/legados
            # contam para o scoring — issue #1098)
            vinculos_result = await session.execute(
                select(VinculoEvidencia)
                .where(
                    VinculoEvidencia.acao_id == acao_id,
                    or_(
                        VinculoEvidencia.estado == EstadoVinculo.aprovado,
                        VinculoEvidencia.estado.is_(None),  # legado sem estado
                    ),
                )
                .options(joinedload(VinculoEvidencia.evidencia).joinedload(Evidencia.fonte))
            )
            vinculos = list(vinculos_result.unique().scalars())

            evidencias = []
            for v in vinculos:
                ev = v.evidencia
                if ev:
                    log_evidence_access(ev.id, "GET /api/v1/scoring/acoes/{acao_id}/status")
                    evidencias.append(
                        {
                            "id": ev.id,
                            "tipo": ev.tipo.value,
                            "trecho": redact_pii(ev.trecho[:200]) if ev.trecho else None,
                            "resumo": redact_pii(ev.resumo) if ev.resumo else None,
                            "data": str(ev.data_evidencia) if ev.data_evidencia else None,
                            "fonte_url": ev.fonte.url if ev.fonte else None,
                        }
                    )

            # Buscar última avaliação
            avaliacao_result = await session.execute(
                select(Avaliacao)
                .where(Avaliacao.acao_id == acao_id)
                .order_by(desc(Avaliacao.versao))
                .limit(1)
            )
            avaliacao = avaliacao_result.scalar_one_or_none()

            # Buscar último audit log
            audit_result = await session.execute(
                select(AuditLog)
                .where(AuditLog.acao_id == acao_id)
                .order_by(desc(AuditLog.data_criacao))
                .limit(1)
            )
            audit_log = audit_result.scalar_one_or_none()

            return {
                "acao_id": acao_id,
                "acao_nome": acao.nome,
                "status": acao.status.value,
                "justificativa": (
                    avaliacao.justificativa if avaliacao else "Nenhuma avaliação registrada."
                ),
                "avaliado_por": avaliacao.avaliado_por if avaliacao else None,
                "data_avaliacao": (str(avaliacao.data_avaliacao) if avaliacao else None),
                "versao": avaliacao.versao if avaliacao else 0,
                "evidencias": evidencias,
                "evidence_count": len(evidencias),
                "ultimo_audit_log": {
                    "status_anterior": (
                        audit_log.status_anterior.value
                        if audit_log and audit_log.status_anterior
                        else None
                    ),
                    "status_novo": audit_log.status_novo.value if audit_log else None,
                    "data": audit_log.data_criacao.isoformat() if audit_log else None,
                }
                if audit_log
                else None,
            }

    @staticmethod
    async def get_eixo_dashboard(eixo_id: str) -> EixoDashboard:
        """Retorna dashboard de status agregado por eixo.

        Args:
            eixo_id: ID do eixo.

        Returns:
            EixoDashboard com contagens por status.

        Raises:
            ValueError: Se o eixo não for encontrado.
        """
        async with get_session() as session:
            eixo_result = await session.execute(select(Eixo).where(Eixo.id == eixo_id))
            eixo = eixo_result.scalar_one_or_none()
            if not eixo:
                raise ValueError(f"Eixo não encontrado: {eixo_id}")

            # Buscar programas do eixo
            prog_result = await session.execute(
                select(Programa.id).where(Programa.eixo_id == eixo_id)
            )
            programa_ids = [row[0] for row in prog_result]

            if not programa_ids:
                return EixoDashboard(
                    eixo_id=eixo_id,
                    eixo_nome=eixo.nome,
                    total_acoes=0,
                )

            # Buscar ações do eixo
            acoes_result = await session.execute(
                select(Acao).where(Acao.programa_id.in_(programa_ids))
            )
            acoes = list(acoes_result.scalars())

        total = len(acoes)
        status_map: dict[str, int] = {}
        for acao in acoes:
            key = acao.status.value if hasattr(acao.status, "value") else str(acao.status)
            status_map[key] = status_map.get(key, 0) + 1

        status_counts = []
        for status_val, count in status_map.items():
            try:
                status_enum = StatusAcao(status_val)
            except ValueError:
                continue
            pct = round((count / total) * 100, 1) if total > 0 else 0.0
            status_counts.append(StatusCount(status=status_enum, count=count, percentage=pct))

        entregue = status_map.get("entregue", 0) + status_map.get("parcialmente_entregue", 0)
        andamento = status_map.get("em_andamento", 0)

        return EixoDashboard(
            eixo_id=eixo_id,
            eixo_nome=eixo.nome,
            total_acoes=total,
            status_counts=status_counts,
            progresso_entregue=round((entregue / total) * 100, 1) if total > 0 else 0.0,
            progresso_andamento=round((andamento / total) * 100, 1) if total > 0 else 0.0,
        )

    @staticmethod
    async def get_global_dashboard() -> GlobalDashboard:
        """Retorna dashboard global de status de todas as ações.

        Returns:
            GlobalDashboard com contagens por status e por eixo.
        """
        async with get_session() as session:
            # Total de ações
            total_result = await session.execute(select(func.count(Acao.id)))
            total = total_result.scalar() or 0

            # Ações por status
            status_result = await session.execute(
                select(Acao.status, func.count(Acao.id)).group_by(Acao.status)
            )
            status_map = {
                row[0].value if hasattr(row[0], "value") else str(row[0]): row[1]
                for row in status_result
            }

            status_counts = []
            for status_val, count in status_map.items():
                try:
                    status_enum = StatusAcao(status_val)
                except ValueError:
                    continue
                pct = round((count / total) * 100, 1) if total > 0 else 0.0
                status_counts.append(StatusCount(status=status_enum, count=count, percentage=pct))

            # Dashboard por eixo — batch: buscar ações por todos os eixos de uma vez
            eixos_result = await session.execute(select(Eixo))
            eixos = list(eixos_result.scalars())

            acoes_por_eixo: dict[str, list[Acao]] = {}
            if eixos:
                all_acoes_result = await session.execute(select(Acao))
                for acao in all_acoes_result.scalars():
                    prog_result = await session.execute(
                        select(Programa.eixo_id).where(Programa.id == acao.programa_id)
                    )
                    eixo_id = prog_result.scalar_one_or_none()
                    if eixo_id:
                        acoes_por_eixo.setdefault(eixo_id, []).append(acao)

        eixos_dashboard = []
        for eixo in eixos:
            acoes = acoes_por_eixo.get(eixo.id, [])
            total = len(acoes)
            eixo_status_map: dict[str, int] = {}
            for acao in acoes:
                key = acao.status.value if hasattr(acao.status, "value") else str(acao.status)
                eixo_status_map[key] = eixo_status_map.get(key, 0) + 1

            eixo_status_counts = []
            for status_val, count in eixo_status_map.items():
                try:
                    status_enum = StatusAcao(status_val)
                except ValueError:
                    continue
                pct = round((count / total) * 100, 1) if total > 0 else 0.0
                eixo_status_counts.append(
                    StatusCount(status=status_enum, count=count, percentage=pct)
                )

            entregue = eixo_status_map.get("entregue", 0) + eixo_status_map.get(
                "parcialmente_entregue", 0
            )
            andamento = eixo_status_map.get("em_andamento", 0)

            eixos_dashboard.append(
                EixoDashboard(
                    eixo_id=eixo.id,
                    eixo_nome=eixo.nome,
                    total_acoes=total,
                    status_counts=eixo_status_counts,
                    progresso_entregue=(round((entregue / total) * 100, 1) if total > 0 else 0.0),
                    progresso_andamento=(round((andamento / total) * 100, 1) if total > 0 else 0.0),
                )
            )

        entregue = status_map.get("entregue", 0) + status_map.get("parcialmente_entregue", 0)
        progresso = round((entregue / total) * 100, 1) if total > 0 else 0.0

        return GlobalDashboard(
            total_acoes=total,
            status_counts=status_counts,
            eixos=eixos_dashboard,
            progresso_geral=progresso,
        )
