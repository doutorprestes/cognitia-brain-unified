"""Serviço de auditoria — IA Brasil.

Implementa o registro imutável de mudanças de status conforme CONTEXT.md §8.
Cada mudança de status de uma ação é registrada de forma imutável, criando
um histórico completo e rastreável das avaliações ao longo do tempo.

Regras de negócio:
1. AuditLog é imutável: sem UPDATE ou DELETE na tabela
2. AuditLog deve ser chamado dentro da mesma transação que cria a Avaliacao
3. Justificativa é obrigatória em todo log
4. Status anterior e novo são obrigatórios para rastreabilidade
"""

from datetime import date
from typing import Any

from loguru import logger
from sqlalchemy import desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.db import (
    Acao,
    AuditLog,
    StatusAcao,
    get_session,
)
from src.modules.audit.schemas import (
    AuditHistoryRequest,
    AuditHistoryResult,
    AuditLogRead,
)


class AuditService:
    """Serviço para registro e consulta de logs de auditoria."""

    @staticmethod
    async def create_audit_log(  # 6 params are justified for audit completeness
        acao_id: str,
        status_anterior: StatusAcao | None,
        status_novo: StatusAcao,
        justificativa: str,
        criado_por: str = "system",
        extra_data: dict[str, Any] | None = None,
        session: AsyncSession | None = None,
    ) -> AuditLog:
        """Cria um novo registro de auditoria para mudança de status.

        Args:
            acao_id: ID da ação que teve status alterado
            status_anterior: Status anterior da ação (None para primeira avaliação)
            status_novo: Novo status da ação
            justificativa: Justificativa detalhada para a mudança
            criado_por: Autor do registro (system, user_id, ou service_name)
            extra_data: Metadados adicionais (opcional)
            session: Sessão SQLAlchemy (opcional). Se informada, o registro é
                criado na transação do chamador (que gerencia commit/rollback);
                se None, uma nova sessão é aberta via get_session().

        Returns:
            AuditLog: O registro de auditoria criado

        Raises:
            ValueError: Se acao_id não existir ou justificativa estiver vazia
        """
        if not justificativa or not justificativa.strip():
            raise ValueError("Justificativa é obrigatória para registros de auditoria")

        # Combine metadata and extra_data (extra_data takes precedence)
        effective_metadata = extra_data or {}

        async def _insert_log(sess: AsyncSession) -> AuditLog:
            # Verificar se a ação existe
            acao_result = await sess.execute(select(Acao).where(Acao.id == acao_id))
            acao = acao_result.scalar_one_or_none()
            if not acao:
                raise ValueError(f"Ação não encontrada: {acao_id}")

            # Contar audit_logs para gerar ID único sem lazy load
            audit_count = (
                await sess.scalar(select(func.count()).where(AuditLog.acao_id == acao_id)) or 0
            )

            # Criar novo registro de auditoria
            audit_log = AuditLog(
                id=f"audit_{acao_id}_{date.today().isoformat()}_{audit_count + 1}",
                acao_id=acao_id,
                status_anterior=status_anterior,
                status_novo=status_novo,
                justificativa=justificativa.strip(),
                criado_por=criado_por,
                data_criacao=date.today(),
                extra_data=effective_metadata,
            )

            sess.add(audit_log)
            await sess.flush()

            logger.info(
                f"AuditLog criado: {acao_id} {status_anterior} -> {status_novo} por {criado_por}"
            )

            return audit_log

        if session is None:
            async with get_session() as local_session:
                return await _insert_log(local_session)
        return await _insert_log(session)

    @staticmethod
    async def get_audit_history(request: AuditHistoryRequest) -> AuditHistoryResult:
        """Recupera o histórico de auditoria para uma ou mais ações.

        Args:
            request: Filtros para consulta de histórico

        Returns:
            AuditHistoryResult: Resultado com logs de auditoria
        """
        async with get_session() as session:
            # Construir query base
            # Ordenar por data_criacao desc e id desc para garantir ordem cronológica
            # reversa estável (mais recentes primeiro) quando múltiplos logs no mesmo dia
            stmt = select(AuditLog).order_by(desc(AuditLog.data_criacao), desc(AuditLog.id))

            # Aplicar filtros
            if request.acao_id:
                stmt = stmt.where(AuditLog.acao_id == request.acao_id)

            if request.status_anterior:
                stmt = stmt.where(AuditLog.status_anterior == request.status_anterior)

            if request.status_novo:
                stmt = stmt.where(AuditLog.status_novo == request.status_novo)

            if request.criado_por:
                stmt = stmt.where(AuditLog.criado_por == request.criado_por)

            if request.data_inicio:
                stmt = stmt.where(AuditLog.data_criacao >= request.data_inicio)

            if request.data_fim:
                stmt = stmt.where(AuditLog.data_criacao <= request.data_fim)

            # Executar query
            result = await session.execute(stmt)
            audit_logs = list(result.scalars())

            # Converter para schemas
            audit_logs_data = [
                AuditLogRead(
                    id=log.id,
                    acao_id=log.acao_id,
                    status_anterior=log.status_anterior,
                    status_novo=log.status_novo,
                    justificativa=log.justificativa,
                    criado_por=log.criado_por,
                    data_criacao=log.data_criacao,
                    extra_data=log.extra_data,
                )
                for log in audit_logs
            ]

            return AuditHistoryResult(
                audit_logs=audit_logs_data,
                total=len(audit_logs_data),
            )

    @staticmethod
    async def get_audit_history_by_acao(acao_id: str) -> list[AuditLogRead]:
        """Recupera o histórico completo de auditoria para uma ação específica.

        Args:
            acao_id: ID da ação

        Returns:
            List[AuditLogRead]: Lista de registros de auditoria ordenados por data
        """
        result = await AuditService.get_audit_history(AuditHistoryRequest(acao_id=acao_id))
        return result.audit_logs
