"""Pipeline de scoring — IA Brasil.

Orquestrador que calcula status de cada ação do PBIA com base nas
evidências vinculadas, gerando trilha imutável de auditoria.

Fluxo:
1. Para cada ação, coletar todas as evidências vinculadas
2. Aplicar regras da taxonomia de status (rules.py)
3. Gerar avaliação imutável com justificativa textual
4. Registrar em AuditLog com diff do status anterior

Uso:
    pipeline = ScoringPipeline()
    results = await pipeline.run_all()
    result = await pipeline.run_for_acao("acao_id")
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import date
from typing import TYPE_CHECKING, Any

from loguru import logger
from sqlalchemy import desc, func, or_, select
from sqlalchemy import update as sa_update
from sqlalchemy.orm import joinedload

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

from src.core.db import (
    Acao,
    AuditLog,
    Avaliacao,
    EstadoVinculo,
    Evidencia,
    Fonte,
    StatusAcao,
    VinculoEvidencia,
    get_session,
)
from src.modules.scoring.rules import (
    RULE_VERSION,
    EvidenceInfo,
    evaluate_status,
)


@dataclass
class PipelineResult:
    """Resultado do pipeline de scoring para uma ação."""

    acao_id: str
    acao_nome: str
    status_anterior: StatusAcao
    status_novo: StatusAcao
    confidence: float
    justification: str
    rules_applied: list[str] = field(default_factory=list)
    evidence_count: int = 0
    avaliacao_id: str | None = None
    audit_log_id: str | None = None
    avaliacao_criada: bool = True


@dataclass
class PipelineRunResult:
    """Resultado agregado de uma execução completa do pipeline."""

    total: int = 0
    processadas: int = 0
    atualizadas: int = 0
    erros: int = 0
    resultados: list[PipelineResult] = field(default_factory=list)
    erros_detalhes: list[dict[str, Any]] = field(default_factory=list)


class ScoringPipeline:
    """Pipeline orquestrador de cálculo de status.

    Coleta evidências vinculadas a cada ação, aplica regras de negócio
    e registra avaliações e logs de auditoria de forma imutável.
    """

    @staticmethod
    async def _collect_evidence(
        acao_id: str,
        session: AsyncSession | None = None,
    ) -> list[EvidenceInfo]:
        """Coleta todas as evidências vinculadas a uma ação.

        Args:
            acao_id: ID da ação.
            session: Sessão SQLAlchemy opcional. Se None, cria uma nova.

        Returns:
            Lista de EvidenceInfo com dados simplificados das evidências.
        """
        if session is None:
            async with get_session() as s:
                return await ScoringPipeline._collect_evidence_inner(acao_id, s)
        return await ScoringPipeline._collect_evidence_inner(acao_id, session)

    @staticmethod
    async def _collect_evidence_inner(
        acao_id: str,
        session: AsyncSession,
    ) -> list[EvidenceInfo]:
        """Inner helper para coleta de evidências em uma sessão existente.

        Apenas vínculos ``aprovado`` (ou legados sem estado) contam para o
        scoring — vínculos ``proposto``/``rejeitado`` aguardam revisão humana
        e não devem influenciar o status da ação (issue #1098).
        """
        result = await session.execute(
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
        vinculos = list(result.unique().scalars())

        evidencias: list[EvidenceInfo] = []
        for vinculo in vinculos:
            ev = vinculo.evidencia
            if not ev:
                continue
            fonte_tipo = ev.fonte.tipo_documental if ev.fonte else None
            evidencias.append(
                EvidenceInfo(
                    id=ev.id,
                    tipo=ev.tipo,
                    trecho=ev.trecho,
                    resumo=ev.resumo,
                    data_evidencia=ev.data_evidencia,
                    confianca=(float(ev.confianca) if ev.confianca is not None else None),
                    fonte_tipo_documental=fonte_tipo,
                )
            )
        return evidencias

    @staticmethod
    async def _get_financial_execution(
        acao_id: str,
        session: AsyncSession,
    ) -> dict[str, Any] | None:
        """Busca dados de execução financeira para uma ação.

        Combina a execução financeira da CGU (valor_pago/valor_empenhado) com
        o valor previsto no PBIA (Recurso.valor_previsto).

        Args:
            acao_id: ID da ação.
            session: Sessão do banco de dados.

        Returns:
            Dict com valor_pago, valor_empenhado e valor_previsto, ou None.
        """
        try:
            from src.core.db import ExecucaoFinanceira, Recurso

            result = await session.execute(
                select(
                    func.sum(ExecucaoFinanceira.valor_pago).label("total_pago"),
                    func.sum(ExecucaoFinanceira.valor_empenhado).label("total_empenhado"),
                ).where(ExecucaoFinanceira.acao_id == acao_id)
            )
            row = result.one_or_none()
            total_pago = float(row.total_pago) if row and row.total_pago else 0.0
            total_empenhado = float(row.total_empenhado) if row and row.total_empenhado else 0.0

            recurso_result = await session.execute(
                select(func.sum(Recurso.valor_previsto)).where(Recurso.acao_id == acao_id)
            )
            total_previsto = float(recurso_result.scalar() or 0)

            if total_pago <= 0 and total_empenhado <= 0 and total_previsto <= 0:
                return None
            return {
                "valor_pago": total_pago,
                "valor_empenhado": total_empenhado,
                "valor_previsto": total_previsto,
            }
        except Exception:
            return None

    @staticmethod
    def _compute_fingerprint(
        evidencias: list[EvidenceInfo],
        prazo: date | None,
        execucao_financeira: dict[str, Any] | None,
        panel_status: str | None,
    ) -> str:
        """Hash estável dos inputs do pipeline para idempotência.

        Inclui a versão das regras (RULE_VERSION), os ids e o estado das
        evidências usadas, os dados de execução financeira, o status do painel
        e o prazo. Um re-run com o mesmo fingerprint não duplica avaliação.
        """
        payload: dict[str, Any] = {
            "rule_version": RULE_VERSION,
            "prazo": prazo.isoformat() if prazo else None,
            "panel_status": panel_status,
            "execucao_financeira": execucao_financeira,
            "evidencias": sorted(
                (
                    {
                        "id": e.id,
                        "tipo": e.tipo.value,
                        "trecho": e.trecho,
                        "resumo": e.resumo,
                        "data_evidencia": (
                            e.data_evidencia.isoformat() if e.data_evidencia else None
                        ),
                        "confianca": e.confianca,
                        "fonte_tipo_documental": e.fonte_tipo_documental,
                    }
                    for e in evidencias
                ),
                key=lambda item: item["id"],
            ),
        }
        encoded = json.dumps(payload, sort_keys=True, ensure_ascii=True, default=str).encode(
            "utf-8"
        )
        return hashlib.sha256(encoded).hexdigest()

    @staticmethod
    async def _get_panel_status(
        acao_id: str,
        session: AsyncSession,
    ) -> str | None:
        """Busca status do painel oficial do MCTI para uma ação.

        Args:
            acao_id: ID da ação.
            session: Sessão do banco de dados.

        Returns:
            Status do painel ou None.
        """
        try:
            result = await session.execute(
                select(Evidencia.resumo)
                .join(VinculoEvidencia)
                .join(Evidencia.fonte)
                .where(
                    VinculoEvidencia.acao_id == acao_id,
                    or_(
                        VinculoEvidencia.estado == EstadoVinculo.aprovado,
                        VinculoEvidencia.estado.is_(None),  # legado sem estado
                    ),
                )
                .where(Fonte.url.ilike("%monitoramento%"))
                .order_by(Evidencia.data_evidencia.desc())
                .limit(1)
            )
            return result.scalar_one_or_none()
        except Exception:
            return None

    @staticmethod
    async def _get_latest_avaliacao(acao_id: str) -> Avaliacao | None:
        """Busca a avaliação mais recente de uma ação.

        Args:
            acao_id: ID da ação.

        Returns:
            Avaliacao mais recente ou None.
        """
        async with get_session() as session:
            result = await session.execute(
                select(Avaliacao)
                .where(Avaliacao.acao_id == acao_id)
                .order_by(desc(Avaliacao.versao))
                .limit(1)
            )
            return result.scalar_one_or_none()

    @staticmethod
    async def run_for_acao(acao_id: str, force_recalculate: bool = False) -> PipelineResult:
        """Executa o pipeline de scoring para uma ação específica.

        Pipeline idempotente: se o fingerprint dos inputs (evidências e
        recursos usados) não mudou desde a última avaliação, reutiliza a
        avaliação existente em vez de criar duplicata.
        ``force_recalculate=True`` força a criação de uma nova versão.

        Usa uma única sessão do banco para evitar concorrência SQLite.

        Args:
            acao_id: ID da ação a ser avaliada.
            force_recalculate: Se True, recalcula mesmo com inputs inalterados.

        Returns:
            PipelineResult com o resultado da avaliação.

        Raises:
            ValueError: Se a ação não for encontrada.
        """
        async with get_session() as session:
            # 1. Buscar ação
            acao_result = await session.execute(select(Acao).where(Acao.id == acao_id))
            acao = acao_result.scalar_one_or_none()
            if not acao:
                raise ValueError(f"Ação não encontrada: {acao_id}")

            acao_nome = acao.nome
            status_anterior = acao.status
            prazo = acao.prazo

            # 2. Coletar evidências na mesma sessão
            evidencias = await ScoringPipeline._collect_evidence_inner(acao_id, session)

            # 2a. Buscar dados de execução financeira (se disponível)
            execucao_financeira = await ScoringPipeline._get_financial_execution(acao_id, session)

            # 2b. Buscar status do painel oficial (se disponível)
            panel_status = await ScoringPipeline._get_panel_status(acao_id, session)

            # 3. Avaliar status (função pura, sem banco)
            rule_result = evaluate_status(
                evidencias,
                prazo,
                execucao_financeira=execucao_financeira,
                panel_status=panel_status,
            )

            # 4. Fingerprint dos inputs para idempotência
            fingerprint = ScoringPipeline._compute_fingerprint(
                evidencias, prazo, execucao_financeira, panel_status
            )

            # 5. Buscar última versão da avaliação
            latest_result = await session.execute(
                select(Avaliacao)
                .where(Avaliacao.acao_id == acao_id)
                .order_by(desc(Avaliacao.versao))
                .limit(1)
            )
            latest = latest_result.scalar_one_or_none()

            # 5a. Idempotência: inputs inalterados → reutiliza avaliação existente
            if latest and not force_recalculate:
                audit_result = await session.execute(
                    select(AuditLog).where(AuditLog.acao_id == acao_id)
                )
                audit_logs = list(audit_result.scalars())
                audit = next(
                    (
                        log
                        for log in audit_logs
                        if (log.extra_data or {}).get("avaliacao_id") == latest.id
                    ),
                    None,
                )
                if audit and (audit.extra_data or {}).get("fingerprint") == fingerprint:
                    logger.info(
                        f"Scoring pipeline: {acao_id} inputs inalterados — "
                        f"reutilizando avaliação {latest.id}"
                    )
                    return PipelineResult(
                        acao_id=acao_id,
                        acao_nome=acao_nome,
                        status_anterior=latest.status_avaliado,
                        status_novo=rule_result.status,
                        confidence=rule_result.confidence,
                        justification=rule_result.justification,
                        rules_applied=rule_result.rules_applied,
                        evidence_count=len(evidencias),
                        avaliacao_id=latest.id,
                        audit_log_id=audit.id,
                        avaliacao_criada=False,
                    )

            next_version = (latest.versao + 1) if latest else 1

            # 6. Criar avaliação imutável
            avaliacao = Avaliacao(
                id=f"av_scoring_{acao_id}_{next_version}",
                acao_id=acao_id,
                status_avaliado=rule_result.status,
                justificativa=rule_result.justification,
                avaliado_por="scoring_pipeline",
                data_avaliacao=date.today(),
                versao=next_version,
            )
            session.add(avaliacao)
            await session.flush()
            avaliacao_id: str = avaliacao.id

            # 7. Atualizar status da ação
            await session.execute(
                sa_update(Acao).where(Acao.id == acao_id).values(status=rule_result.status)
            )

            # 8. Criar audit log diretamente (evita session extra do AuditService)
            audit_count_stmt = (
                select(func.count()).select_from(AuditLog).where(AuditLog.acao_id == acao_id)
            )
            audit_count: int = await session.scalar(audit_count_stmt) or 0
            audit_log = AuditLog(
                id=f"audit_{acao_id}_{date.today().isoformat()}_{audit_count + 1}",
                acao_id=acao_id,
                status_anterior=status_anterior,
                status_novo=rule_result.status,
                justificativa=f"Scoring pipeline: {rule_result.justification}",
                criado_por="scoring_pipeline",
                data_criacao=date.today(),
                extra_data={
                    "avaliacao_id": avaliacao_id,
                    "versao_avaliacao": next_version,
                    "rule_version": RULE_VERSION,
                    "fingerprint": fingerprint,
                    "confidence": rule_result.confidence,
                    "rules_applied": rule_result.rules_applied,
                    "evidence_count": len(evidencias),
                },
            )
            session.add(audit_log)
            await session.flush()
            audit_log_id: str = audit_log.id

            # Context manager faz commit automático ao sair

        logger.info(
            f"Scoring pipeline: {acao_id} {status_anterior.value} -> "
            f"{rule_result.status.value} (v{next_version})"
        )

        return PipelineResult(
            acao_id=acao_id,
            acao_nome=acao_nome,
            status_anterior=status_anterior,
            status_novo=rule_result.status,
            confidence=rule_result.confidence,
            justification=rule_result.justification,
            rules_applied=rule_result.rules_applied,
            evidence_count=len(evidencias),
            avaliacao_id=avaliacao_id,
            audit_log_id=audit_log_id,
            avaliacao_criada=True,
        )

    @staticmethod
    async def run_all(force_recalculate: bool = False) -> PipelineRunResult:
        """Executa o pipeline de scoring para todas as ações.

        Pipeline idempotente: re-run não duplica avaliações quando os inputs
        (evidências e recursos usados) não mudaram.

        Args:
            force_recalculate: Se True, força recálculo de todas as ações.

        Returns:
            PipelineRunResult com resultado agregado.
        """
        run_result = PipelineRunResult()

        async with get_session() as session:
            result = await session.execute(select(Acao.id, Acao.nome))
            acoes = [(row[0], row[1]) for row in result]

        run_result.total = len(acoes)
        logger.info(f"Pipeline de scoring: processando {len(acoes)} ações")

        for acao_id, acao_nome in acoes:
            try:
                pipeline_result = await ScoringPipeline.run_for_acao(
                    acao_id, force_recalculate=force_recalculate
                )
                run_result.resultados.append(pipeline_result)
                run_result.processadas += 1
                if pipeline_result.status_anterior != pipeline_result.status_novo:
                    run_result.atualizadas += 1
            except Exception as e:
                logger.error(f"Erro ao processar ação {acao_id}: {e}")
                run_result.erros += 1
                run_result.erros_detalhes.append(
                    {
                        "acao_id": acao_id,
                        "acao_nome": acao_nome,
                        "erro": str(e),
                    }
                )

        logger.info(
            f"Pipeline de scoring concluído: "
            f"{run_result.processadas}/{run_result.total} processadas, "
            f"{run_result.atualizadas} atualizadas, {run_result.erros} erros"
        )

        return run_result

    @staticmethod
    async def run_for_eixo(eixo_id: str, force_recalculate: bool = False) -> PipelineRunResult:
        """Executa o pipeline de scoring para todas as ações de um eixo.

        Args:
            eixo_id: ID do eixo.
            force_recalculate: Se True, força recálculo das ações do eixo.

        Returns:
            PipelineRunResult com resultado agregado.
        """
        run_result = PipelineRunResult()

        async with get_session() as session:
            from src.core.db import Eixo, Programa

            eixo_result = await session.execute(select(Eixo).where(Eixo.id == eixo_id))
            eixo = eixo_result.scalar_one_or_none()
            if not eixo:
                raise ValueError(f"Eixo não encontrado: {eixo_id}")

            # Buscar ações do eixo via programas
            programas_result = await session.execute(
                select(Programa.id).where(Programa.eixo_id == eixo_id)
            )
            programa_ids = [row[0] for row in programas_result]

            if not programa_ids:
                return run_result

            acoes_result = await session.execute(
                select(Acao.id, Acao.nome).where(Acao.programa_id.in_(programa_ids))
            )
            acoes = [(row[0], row[1]) for row in acoes_result]

        run_result.total = len(acoes)

        for acao_id, acao_nome in acoes:
            try:
                pipeline_result = await ScoringPipeline.run_for_acao(
                    acao_id, force_recalculate=force_recalculate
                )
                run_result.resultados.append(pipeline_result)
                run_result.processadas += 1
                if pipeline_result.status_anterior != pipeline_result.status_novo:
                    run_result.atualizadas += 1
            except Exception as e:
                logger.error(f"Erro ao processar ação {acao_id}: {e}")
                run_result.erros += 1
                run_result.erros_detalhes.append(
                    {
                        "acao_id": acao_id,
                        "acao_nome": acao_nome,
                        "erro": str(e),
                    }
                )

        return run_result
