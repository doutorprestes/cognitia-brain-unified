"""Serviço de scoring — IA Brasil.

Implementa o cálculo de status conforme a taxonomia do CONTEXT.md §9.
Regras de negócio (domain-model.md):
1. Toda avaliação deve ter ao menos uma evidência vinculada (exceto status 'Não iniciado')
2. Todo status é derivado de regra explícita, nunca por inferência opaca
3. O trecho exato da evidência que sustenta a conclusão deve estar registrado
4. Mudanças de status são imutáveis — novas avaliações criam novos registros

Taxonomia de status (CONTEXT.md §9):
- Não iniciado: Nenhuma evidência pública confiável de execução encontrada
- Sinalizado: Há anúncio ou intenção, mas sem ato ou entrega concreta
- Em andamento: Evidência de execução material (edital, contratação, lançamento parcial)
- Parcialmente entregue: Parte mensurável da meta cumprida, mas não o todo
- Entregue: Evidência robusta e suficiente de cumprimento da meta
- Inconclusivo: Evidências insuficientes, vagas ou sem vinculação segura
- Contraditório: Fontes públicas apontando conclusões incompatíveis
- Descontinuado: Revogação, suspensão ou abandono explícito
"""

import asyncio
import subprocess
import time
from datetime import date
from pathlib import Path
from typing import Any

from loguru import logger
from sqlalchemy import desc, func, select
from sqlalchemy import update as sa_update

from src.core.db import (
    Acao,
    AuditLog,
    Avaliacao,
    EstadoVinculo,
    Evidencia,
    StatusAcao,
    TipoEvidencia,
    get_session,
)
from src.modules.audit.service import AuditService
from src.modules.linking.service import LinkingService
from src.modules.scoring.pipeline import ScoringPipeline
from src.modules.scoring.rules import evaluate_status
from src.modules.scoring.schemas import (
    BulkScoringRequest,
    BulkScoringResult,
    ScoringRequest,
    ScoringResult,
    StatusCalculation,
)
from src.modules.webhook.outbound import notify_status_changed

# ---------------------------------------------------------------------------
# Pesos por tipo de evidência (confiança)
# ---------------------------------------------------------------------------

EVIDENCE_WEIGHTS: dict[TipoEvidencia, float] = {
    TipoEvidencia.ato_oficial: 1.0,  # Mais confiável
    TipoEvidencia.edital: 1.0,
    TipoEvidencia.relatorio: 0.9,
    TipoEvidencia.pagina_institucional: 0.8,
    TipoEvidencia.noticia: 0.6,  # Menos confiável
    TipoEvidencia.outro: 0.5,
}

# ---------------------------------------------------------------------------
# Notificação de mudança de status via Telegram
# ---------------------------------------------------------------------------

NOTIFY_SCRIPT = str(Path(__file__).resolve().parents[3] / "scripts" / "notify-telegram.sh")
NOTIFY_MIN_INTERVAL = 1.0  # segundos entre notificações (rate limiting)
_NOTIFY_LOCK = asyncio.Lock()
_LAST_NOTIFY_STATE: list[float] = [0.0]  # [último envio em monotonic()]


async def _notify_status_change(
    acao_nome: str,
    status_anterior: StatusAcao | None,
    status_novo: StatusAcao,
    trecho_original: str | None,
) -> None:
    """Envia notificação de mudança de status via scripts/notify-telegram.sh.

    Usa rate limiting de 1s entre chamadas e nunca deve interromper o fluxo
    principal de atualização de status (falhas são apenas registradas).
    """
    anterior = status_anterior.value if status_anterior is not None else "—"
    novo = status_novo.value
    mensagem = (
        f"Mudança de status\n"
        f"Ação: {acao_nome}\n"
        f"Anterior: {anterior}\n"
        f"Novo: {novo}\n"
        f"Trecho: {trecho_original or '—'}"
    )
    async with _NOTIFY_LOCK:
        now = time.monotonic()
        wait = NOTIFY_MIN_INTERVAL - (now - _LAST_NOTIFY_STATE[0])
        if wait > 0:
            await asyncio.sleep(wait)
        _LAST_NOTIFY_STATE[0] = time.monotonic()
    try:
        await asyncio.to_thread(
            subprocess.run,
            ["bash", NOTIFY_SCRIPT, mensagem],
            shell=False,
            check=False,
            capture_output=True,
        )
    except Exception as e:  # notificação não deve quebrar o fluxo principal
        logger.warning(f"Falha ao notificar mudança de status via Telegram: {e}")


# ---------------------------------------------------------------------------
# Regras de scoring
# ---------------------------------------------------------------------------


class ScoringService:
    """Serviço para cálculo automático de status."""

    @staticmethod
    async def calculate_status_for_acao(acao_id: str) -> StatusCalculation:
        """Calcula o status para uma ação específica.

        Usa o mesmo motor de regras do pipeline persistido
        (rules.evaluate_status) e os mesmos inputs (evidências, execução
        financeira e painel oficial), garantindo que o resultado de
        /scoring/calculate == resultado persistido pelo pipeline.

        Retorna StatusCalculation com:
        - proposed_status: status sugerido
        - confidence: confiança (0.0-1.0)
        - rules_applied: lista de regras aplicadas
        - justification: justificativa detalhada
        """
        async with get_session() as session:
            # Buscar ação
            acao_result = await session.execute(select(Acao).where(Acao.id == acao_id))
            acao = acao_result.scalar_one_or_none()
            if not acao:
                raise ValueError(f"Ação não encontrada: {acao_id}")

            # Coletar os mesmos inputs usados pelo pipeline persistido
            evidencias = await ScoringPipeline._collect_evidence_inner(acao_id, session)
            execucao_financeira = await ScoringPipeline._get_financial_execution(acao_id, session)
            panel_status = await ScoringPipeline._get_panel_status(acao_id, session)

            # Aplicar regras canônicas (mesmas do pipeline persistido)
            rule_result = evaluate_status(
                evidencias,
                acao.prazo,
                execucao_financeira=execucao_financeira,
                panel_status=panel_status,
            )

            # Buscar a avaliação mais recente para o status atual
            latest_result = await session.execute(
                select(Avaliacao)
                .where(Avaliacao.acao_id == acao_id)
                .order_by(desc(Avaliacao.data_avaliacao), desc(Avaliacao.versao))
                .limit(1)
            )
            latest_avaliacao = latest_result.scalar_one_or_none()

            current_status = (
                latest_avaliacao.status_avaliado.value if latest_avaliacao else acao.status.value
            )

            datas_evidencias = [
                e.data_evidencia for e in evidencias if e.data_evidencia is not None
            ]
            latest_date = max(datas_evidencias) if datas_evidencias else None

            return StatusCalculation(
                acao_id=acao_id,
                current_status=current_status,
                proposed_status=rule_result.status.value,
                confidence=rule_result.confidence,
                rules_applied=rule_result.rules_applied,
                justification=rule_result.justification,
                evidence_count=len(evidencias),
                latest_evidence_date=latest_date,
            )

    @staticmethod
    async def calculate_scoring(request: ScoringRequest) -> ScoringResult:
        """Calcula o scoring para uma requisição específica."""
        calculation = await ScoringService.calculate_status_for_acao(request.acao_id)

        # Buscar evidências de suporte — apenas vínculos aprovados (ou legados
        # sem estado) influenciam o scoring (issue #1098)
        supporting_evidence: list[dict[str, Any]] = []
        conflicting_evidence: list[dict[str, Any]] = []

        vinculos = [
            v
            for v in await LinkingService.get_links_by_acao(request.acao_id)
            if v.estado == EstadoVinculo.aprovado or v.estado is None
        ]

        evidencias_map: dict[str, Evidencia] = {
            v.evidencia_id: v.evidencia for v in vinculos if v.evidencia is not None
        }

        for v in vinculos:
            evidencia = evidencias_map.get(v.evidencia_id)
            if evidencia:
                weight = EVIDENCE_WEIGHTS.get(evidencia.tipo, 0.5)
                evidence_data = {
                    "id": evidencia.id,
                    "tipo": evidencia.tipo.value,
                    "trecho": evidencia.trecho[:200] if evidencia.trecho else None,
                    "data": (str(evidencia.data_evidencia) if evidencia.data_evidencia else None),
                    "peso": weight,
                    "justificativa_vinculo": v.justificativa,
                }

                if weight >= 0.8:
                    supporting_evidence.append(evidence_data)
                else:
                    conflicting_evidence.append(evidence_data)

        return ScoringResult(
            acao_id=request.acao_id,
            status=calculation.proposed_status,
            calculation=calculation,
            supporting_evidence=supporting_evidence,
            conflicting_evidence=conflicting_evidence,
        )

    @staticmethod
    async def calculate_bulk_scoring(request: BulkScoringRequest) -> BulkScoringResult:
        """Calcula scoring em lote para múltiplas ações."""
        async with get_session() as session:
            # Determinar quais ações processar
            if request.acao_ids:
                acao_ids = request.acao_ids
            else:
                # Buscar todas as ações (com filtros opcionais)
                stmt = select(Acao.id)
                if request.eixo_id:
                    stmt = stmt.join(Acao.programa).join(Acao.programa.eixo)
                    stmt = stmt.where(Acao.programa.eixo_id == request.eixo_id)
                if request.programa_id:
                    stmt = stmt.where(Acao.programa_id == request.programa_id)

                result = await session.execute(stmt)
                acao_ids = [row[0] for row in result]

            results: list[ScoringResult] = []
            failed = 0

            for acao_id in acao_ids:
                try:
                    result = await ScoringService.calculate_scoring(ScoringRequest(acao_id=acao_id))  # type: ignore[assignment]
                    results.append(result)  # type: ignore[arg-type]
                except Exception as e:
                    logger.error(f"Erro ao calcular scoring para ação {acao_id}: {e}")
                    failed += 1

            return BulkScoringResult(
                results=results,
                total=len(acao_ids),
                processed=len(results),
                failed=failed,
            )

    @staticmethod
    async def update_acao_status(acao_id: str, status: StatusAcao, justificativa: str) -> Avaliacao:
        """Atualiza o status de uma ação criando uma nova avaliação.

        Segundo regra de negócio: mudanças de status são imutáveis.
        Sempre cria um novo registro de avaliação e um registro de auditoria.
        """
        async with get_session() as session:
            # Buscar a última avaliação para incrementar versão
            latest_result = await session.execute(
                select(Avaliacao)
                .where(Avaliacao.acao_id == acao_id)
                .order_by(desc(Avaliacao.versao))
                .limit(1)
            )
            latest = latest_result.scalar_one_or_none()
            next_version = (latest.versao + 1) if latest else 1

            # Buscar o status atual da ação para o audit log
            acao_result = await session.execute(select(Acao).where(Acao.id == acao_id))
            acao = acao_result.scalar_one_or_none()
            # Check if there are existing audit logs for this action
            audit_count_result = await session.execute(
                select(func.count()).select_from(AuditLog).where(AuditLog.acao_id == acao_id)
            )
            audit_count = audit_count_result.scalar() or 0
            # If no previous audit logs, treat as first change with no previous status
            status_anterior = None if audit_count == 0 else acao.status if acao else None

            avaliacao = Avaliacao(
                id=f"av_acao_{hash(acao_id) % 1000000:06d}_v{next_version}",
                acao_id=acao_id,
                status_avaliado=status,
                justificativa=justificativa,
                avaliado_por="scoring_automatico",
                data_avaliacao=date.today(),
                versao=next_version,
            )
            session.add(avaliacao)
            await session.flush()

            # Atualizar o status da ação
            await session.execute(sa_update(Acao).where(Acao.id == acao_id).values(status=status))

            # Criar registro de auditoria na MESMA transação (sessão única),
            # garantindo rollback atômico de avaliação + status + audit log
            audit_log = await AuditService.create_audit_log(
                acao_id=acao_id,
                status_anterior=status_anterior,
                status_novo=status,
                justificativa=f"Mudança automática via scoring: {justificativa}",
                criado_por="scoring_automatico",
                extra_data={
                    "avaliacao_id": avaliacao.id,
                    "versao_avaliacao": next_version,
                },
                session=session,
            )

            await session.commit()
            logger.info(
                f"Status da ação {acao_id} atualizado para {status.value} (v{next_version}) "
                f"com AuditLog {audit_log.id}"
            )

            # Notificar a mudança de status via Telegram (não bloqueia o fluxo)
            await _notify_status_change(
                acao_nome=acao.nome if acao else acao_id,
                status_anterior=status_anterior,
                status_novo=status,
                trecho_original=acao.trecho_original if acao else None,
            )

            # Disparar webhook outbound assinado (inativo por padrão — não bloqueia)
            await notify_status_changed(
                {
                    "acao_id": acao_id,
                    "acao_nome": acao.nome if acao else acao_id,
                    "status_anterior": (
                        status_anterior.value if status_anterior is not None else None
                    ),
                    "status_novo": status.value,
                    "justificativa": justificativa,
                    "avaliacao_id": avaliacao.id,
                    "versao_avaliacao": next_version,
                }
            )

            return avaliacao

    @staticmethod
    def get_evidence_weight(tipo: TipoEvidencia) -> float:
        """Retorna o peso de confiança para um tipo de evidência."""
        return EVIDENCE_WEIGHTS.get(tipo, 0.5)
