"""IA Brasil — Timeline Router para Ações.

Endpoints para consulta de timeline de uma ação específica:
- GET /acoes/{acao_id}/timeline - Timeline para uma ação específica (público)
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, cast

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from loguru import logger
from sqlalchemy import func, select

from src.core.limiter import RATE_LIMIT_PUBLIC_READ, limiter

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator

    from sqlalchemy.ext.asyncio import AsyncSession

from src.core.db import Acao, AuditLog, Evento, get_session
from src.modules.public_portal.schemas import ErrorDetail, ErrorResponse
from src.modules.timeline.router import (
    EventoBase,
    StatusChangeBase,
    TimelineItem,
    TimelineListResponse,
)

router = APIRouter(prefix="/acoes")


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """Dependency para obter sessão do banco."""
    async with get_session() as session:
        yield session


def _build_timeline_item(
    *,
    item_id: str,
    tipo: str,
    data: str,
    acao_id: str | None,
    acao_nome: str,
    titulo: str,
    descricao: str,
    detalhes: EventoBase | StatusChangeBase,
) -> dict[str, Any]:
    """Constrói o dict de item de timeline compartilhado pelos dois tipos."""
    return {
        "id": item_id,
        "tipo": tipo,
        "data": data,
        "acao_id": acao_id,
        "acao_nome": acao_nome,
        "titulo": titulo,
        "descricao": descricao,
        "detalhes": detalhes,
    }


async def _count_eventos(session: AsyncSession, acao_id: str) -> int:
    """Conta eventos da ação (paginação no banco)."""
    return (
        await session.execute(
            select(func.count()).select_from(Evento).where(Evento.acao_id == acao_id)
        )
    ).scalar() or 0


async def _count_changes(session: AsyncSession, acao_id: str) -> int:
    """Conta mudanças de status da ação (paginação no banco)."""
    return (
        await session.execute(
            select(func.count()).select_from(AuditLog).where(AuditLog.acao_id == acao_id)
        )
    ).scalar() or 0


async def _load_eventos_page(
    session: AsyncSession,
    acao_id: str,
    acao_nome: str,
    offset: int,
    limit: int,
) -> list[dict[str, Any]]:
    """Carrega eventos paginados no banco (sem carregar a timeline inteira)."""
    result = await session.execute(
        select(Evento)
        .where(Evento.acao_id == acao_id)
        .order_by(Evento.data_evento.desc())
        .offset(offset)
        .limit(limit)
    )
    items: list[dict[str, Any]] = []
    for evento in result.scalars().all():
        items.append(
            _build_timeline_item(
                item_id=evento.id,
                tipo="evento",
                data=evento.data_evento.isoformat(),
                acao_id=evento.acao_id,
                acao_nome=acao_nome,
                titulo=f"[{evento.tipo}] {acao_nome}",
                descricao=evento.descricao,
                detalhes=EventoBase.model_validate(evento),
            )
        )
    return items


async def _load_changes_page(
    session: AsyncSession,
    acao_id: str,
    acao_nome: str,
    offset: int,
    limit: int,
) -> list[dict[str, Any]]:
    """Carrega mudanças de status paginadas no banco."""
    result = await session.execute(
        select(AuditLog)
        .where(AuditLog.acao_id == acao_id)
        .order_by(AuditLog.data_criacao.desc())
        .offset(offset)
        .limit(limit)
    )
    items: list[dict[str, Any]] = []
    for change in result.scalars().all():
        status_anterior = change.status_anterior.value if change.status_anterior else None
        status_novo = change.status_novo.value
        items.append(
            _build_timeline_item(
                item_id=change.id,
                tipo="status_change",
                data=change.data_criacao.isoformat(),
                acao_id=change.acao_id,
                acao_nome=acao_nome,
                titulo=f"Status alterado: {acao_nome}",
                descricao=f"De {status_anterior} para {status_novo}",
                detalhes=StatusChangeBase.model_validate(change),
            )
        )
    return items


@router.get("/{acao_id}/timeline", response_model=TimelineListResponse | ErrorResponse)
@limiter.limit(RATE_LIMIT_PUBLIC_READ)
async def get_timeline_for_action(
    request: Request,
    acao_id: str,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=200),
    tipo: str | None = Query(default=None, description="Filtrar por tipo: evento, status_change"),
    session: AsyncSession = Depends(get_db),
) -> TimelineListResponse | ErrorResponse:
    """Obter timeline para uma ação específica.

    Retorna uma lista cronológica combinando eventos e mudanças de status
    para uma ação específica. A paginação é feita no banco (LIMIT/OFFSET),
    em vez de carregar toda a timeline e fatiar em memória.

    Args:
        acao_id: ID da ação
        page: Número da página (padrão: 1)
        page_size: Itens por página (padrão: 50, máximo: 200)
        tipo: Filtrar por tipo (evento, status_change)

    Returns:
        TimelineListResponse com itens filtrados pela ação
    """
    try:
        # Verificar se a ação existe
        acao_result = await session.execute(select(Acao).where(Acao.id == acao_id))
        acao = acao_result.scalar_one_or_none()
        if acao is None:
            raise HTTPException(status_code=404, detail=f"Ação não encontrada: {acao_id}")
        acao_nome = acao.nome

        offset = (page - 1) * page_size

        if tipo == "evento":
            total = await _count_eventos(session, acao_id)
            if total == 0:
                return TimelineListResponse(data=[], total=0)
            items = await _load_eventos_page(session, acao_id, acao_nome, offset, page_size)
            return TimelineListResponse(
                data=[TimelineItem(**item) for item in items],
                total=total,
            )

        if tipo == "status_change":
            total = await _count_changes(session, acao_id)
            if total == 0:
                return TimelineListResponse(data=[], total=0)
            items = await _load_changes_page(session, acao_id, acao_nome, offset, page_size)
            return TimelineListResponse(
                data=[TimelineItem(**item) for item in items],
                total=total,
            )

        if tipo is not None:
            # Tipo desconhecido: nenhum item corresponde
            return TimelineListResponse(data=[], total=0)

        total = await _count_eventos(session, acao_id) + await _count_changes(session, acao_id)

        if total == 0:
            return TimelineListResponse(data=[], total=0)

        # Merge pagination: buscar o suficiente de cada fonte (ordenadas por data)
        sql_limit = offset + page_size
        eventos_items = await _load_eventos_page(session, acao_id, acao_nome, 0, sql_limit)
        changes_items = await _load_changes_page(session, acao_id, acao_nome, 0, sql_limit)

        merged = [*eventos_items, *changes_items]
        merged.sort(key=lambda x: cast("str", x["data"]), reverse=True)
        paginated = merged[offset : offset + page_size]

        return TimelineListResponse(
            data=[TimelineItem(**item) for item in paginated],
            total=total,
        )
    except HTTPException:
        raise
    except Exception:
        logger.error("Erro ao obter timeline para ação {}", acao_id, exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=ErrorDetail(
                message="Erro interno do servidor",
                code="INTERNAL_ERROR",
            ).model_dump(),
        )
