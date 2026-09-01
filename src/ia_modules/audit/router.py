"""IA Brasil — Audit Router.

Endpoints para consulta do histórico de auditoria de ações:
- GET /audit/acoes/{acao_id} - Histórico de mudanças de status (autenticado)
- GET /audit/{acao_id}/history - Histórico completo via pipeline (público)
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

import sqlalchemy as sa
import sqlalchemy.exc as sa_exc
from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy import desc, select

from src.core.limiter import RATE_LIMIT_AUTHENTICATED, RATE_LIMIT_PUBLIC_AUDIT, limiter

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator

    from sqlalchemy.ext.asyncio import AsyncSession

from src.core.db import AuditLog, get_session
from src.modules.audit.pipeline import AuditPipeline
from src.modules.audit.schemas import AuditDiffRead, AuditHistoryResponse, AuditLogRead
from src.modules.auth.dependencies import verify_api_key

router = APIRouter(prefix="/audit")

logger = logging.getLogger(__name__)

# ============================================================================
# Utilitários
# ============================================================================


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """Dependency para obter sessão do banco."""
    async with get_session() as session:
        yield session


# ============================================================================
# Endpoints - Audit
# ============================================================================


@router.get("/acoes/{acao_id}", response_model=list[AuditLogRead])
@limiter.limit(RATE_LIMIT_AUTHENTICATED)
async def get_audit_history(
    request: Request,
    acao_id: str,
    page: int = Query(default=1, ge=1, description="Número da página"),
    page_size: int = Query(default=20, ge=1, le=100, description="Itens por página"),
    _: str = Depends(verify_api_key),  # Requer autenticação via API Key
    session: AsyncSession = Depends(get_db),
) -> list[AuditLogRead]:
    """Obter histórico de auditoria para uma ação.

    Retorna todos os registros de auditoria (mudanças de status) para uma ação,
    ordenados por data (mais recente primeiro). Requer autenticação.

    Args:
        acao_id: ID da ação
        page: Número da página (padrão: 1)
        page_size: Itens por página (padrão: 20, máximo: 100)

    Returns:
        Lista de registros de auditoria ordenados por data

    Raises:
        HTTPException: 404 se ação não encontrada ou sem registros
        HTTPException: 401 se não autenticado
    """
    try:
        # Contar total de registros para esta ação
        count_result = await session.execute(
            select(sa.func.count(AuditLog.id)).where(AuditLog.acao_id == acao_id)
        )
        total_records = count_result.scalar() or 0

        if total_records == 0:
            raise HTTPException(
                status_code=404,
                detail=f"Nenhum registro de auditoria encontrado para ação: {acao_id}",
            )

        # Obter página de registros
        offset = (page - 1) * page_size
        result = await session.execute(
            select(AuditLog)
            .where(AuditLog.acao_id == acao_id)
            .order_by(desc(AuditLog.data_criacao))
            .offset(offset)
            .limit(page_size)
        )
        audit_logs = result.scalars().all()

        # Converter para schema
        return [
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

    except HTTPException:
        raise
    except sa_exc.IntegrityError:
        logger.warning(
            "IntegrityError ao obter histórico de auditoria para ação %s",
            acao_id,
        )
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Conflito: registro duplicado ou violação de restrição",
        )
    except sa_exc.OperationalError:
        logger.exception(
            "Erro de conexão ao obter histórico de auditoria para ação %s",
            acao_id,
        )
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Serviço de banco de dados temporariamente indisponível",
        )
    except sa_exc.SQLAlchemyError:
        logger.exception(
            "Erro de banco ao obter histórico de auditoria para ação %s",
            acao_id,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Erro interno ao obter histórico de auditoria",
        )
    except Exception:
        logger.exception(
            "Erro inesperado ao obter histórico de auditoria para ação %s",
            acao_id,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Erro interno ao obter histórico de auditoria",
        )


# ============================================================================
# Endpoints - Audit Pipeline (públicos)
# ============================================================================


@router.get(
    "/{acao_id}/history",
    response_model=AuditHistoryResponse,
)
@limiter.limit(RATE_LIMIT_PUBLIC_AUDIT)
async def get_audit_history_pipeline(
    request: Request,
    acao_id: str,
) -> AuditHistoryResponse:
    """Retorna histórico completo de mudanças de status via pipeline.

    Endpoint público que usa o AuditPipeline para retornar
    o histórico completo de auditoria de uma ação.

    Args:
        acao_id: ID da ação.

    Returns:
        AuditHistoryResponse com histórico de mudanças.

    Raises:
        HTTPException: 404 se ação não encontrada
    """
    try:
        history = await AuditPipeline.get_history(acao_id)

        if history.total_mudancas == 0:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=(f"Nenhum registro de auditoria encontrado para ação: {acao_id}"),
            )

        return AuditHistoryResponse(
            acao_id=history.acao_id,
            total_mudancas=history.total_mudancas,
            mudancas=[
                AuditDiffRead(
                    status_anterior=m.status_anterior,
                    status_novo=m.status_novo,
                    data_mudanca=m.data_mudanca,
                    justificativa=m.justificativa,
                    criado_por=m.criado_por,
                    versao=m.versao,
                )
                for m in history.mudancas
            ],
        )
    except HTTPException:
        raise
    except sa_exc.OperationalError:
        logger.exception(
            "Erro de conexão ao obter histórico de auditoria para ação %s",
            acao_id,
        )
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Serviço de banco de dados temporariamente indisponível",
        )
    except sa_exc.SQLAlchemyError:
        logger.exception(
            "Erro de banco ao obter histórico de auditoria para ação %s",
            acao_id,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Erro interno ao obter histórico de auditoria",
        )
