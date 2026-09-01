"""IA Brasil — Timeline Router.

Endpoints para consulta de timeline de eventos e mudanças de status:
- GET /acoes/{acao_id}/timeline - Timeline de uma ação específica
- GET /timeline/events - Listar eventos
- GET /timeline/status-changes - Listar mudanças de status
- GET /timeline - Timeline combinado (eventos + mudanças de status)
"""

from __future__ import annotations

from datetime import date  # noqa: TC003
from typing import TYPE_CHECKING, Any, cast

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from loguru import logger
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.orm import joinedload

from src.core.limiter import RATE_LIMIT_PUBLIC_READ, limiter

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator

    from sqlalchemy.ext.asyncio import AsyncSession

from src.core.db import Acao, AuditLog, Evento, get_session
from src.modules.public_portal.schemas import ErrorDetail, ErrorResponse

router = APIRouter(prefix="/timeline")
acao_timeline_router = APIRouter(prefix="/acoes")

# ============================================================================
# Schemas
# ============================================================================


class EventoBase(BaseModel):
    """Schema base para Evento."""

    model_config = {"from_attributes": True}

    id: str
    acao_id: str | None = None
    tipo: str
    descricao: str
    data_evento: date
    fonte_url: str | None = None

    def model_post_init(self, _context: object) -> None:
        """Normalize tipo to lowercase for frontend compatibility."""
        self.tipo = self.tipo.lower()


class StatusChangeBase(BaseModel):
    """Schema base para mudança de status."""

    model_config = {"from_attributes": True}

    id: str
    acao_id: str | None = None
    status_anterior: str | None = None
    status_novo: str
    data_criacao: date
    justificativa: str


class TimelineItem(BaseModel):
    """Item de timeline (evento ou mudança de status)."""

    id: str
    tipo: str  # 'evento' ou 'status_change'
    data: str
    acao_id: str | None = None
    acao_nome: str
    titulo: str
    descricao: str
    detalhes: EventoBase | StatusChangeBase


class TimelineListResponse(BaseModel):
    """Resposta para listagem de timeline."""

    data: list[TimelineItem]
    total: int


# ============================================================================
# Utilitários
# ============================================================================


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """Dependency para obter sessão do banco."""
    async with get_session() as session:
        yield session


# ============================================================================
# Endpoints
# ============================================================================


@router.get("/events", response_model=list[EventoBase] | ErrorResponse)
@limiter.limit(RATE_LIMIT_PUBLIC_READ)
async def list_events(
    request: Request,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=200),
    session: AsyncSession = Depends(get_db),
) -> list[EventoBase] | ErrorResponse:
    """Listar eventos.

    Retorna uma lista paginada de todos os eventos do PBIA.

    Parâmetros:
    - page: Número da página (padrão: 1)
    - page_size: Itens por página (padrão: 50, máximo: 200)
    """
    try:
        offset = (page - 1) * page_size
        result = await session.execute(
            select(Evento).order_by(Evento.data_evento.desc()).offset(offset).limit(page_size)
        )
        eventos = result.scalars().all()
        return [EventoBase.model_validate(evento) for evento in eventos]
    except HTTPException:
        raise
    except Exception:
        logger.error("Erro ao listar eventos", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=ErrorDetail(
                message="Erro interno do servidor",
                code="INTERNAL_ERROR",
            ).model_dump(),
        )


@router.get("/status-changes", response_model=list[StatusChangeBase] | ErrorResponse)
@limiter.limit(RATE_LIMIT_PUBLIC_READ)
async def list_status_changes(
    request: Request,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=200),
    session: AsyncSession = Depends(get_db),
) -> list[StatusChangeBase] | ErrorResponse:
    """Listar mudanças de status.

    Retorna uma lista paginada de todas as mudanças de status do PBIA.

    Parâmetros:
    - page: Número da página (padrão: 1)
    - page_size: Itens por página (padrão: 50, máximo: 200)
    """
    try:
        offset = (page - 1) * page_size
        result = await session.execute(
            select(AuditLog).order_by(AuditLog.data_criacao.desc()).offset(offset).limit(page_size)
        )
        changes = result.scalars().all()
        return [StatusChangeBase.model_validate(change) for change in changes]
    except HTTPException:
        raise
    except Exception:
        logger.error("Erro ao listar mudanças de status", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=ErrorDetail(
                message="Erro interno do servidor",
                code="INTERNAL_ERROR",
            ).model_dump(),
        )


def _resolve_timeline_acao_nome(acao: Acao | None, acao_id: str | None) -> str:
    """Resolve o nome de exibição da ação para itens de timeline.

    Eventos de nível de plano (acao_id vazio) retornam 'Plano PBIA'
    em vez de uma mensagem de 'não encontrada'.
    """
    if acao is not None:
        return acao.nome
    if acao_id:
        return f"Ação {acao_id}"
    return "Plano PBIA"


async def _load_eventos_page(
    session: AsyncSession,
    offset: int,
    limit: int,
) -> list[dict[str, Any]]:
    """Load eventos with SQL-level pagination.

    Uses ``joinedload`` to fetch the associated action in the same query,
    avoiding a full scan of the actions table per request.
    """
    result = await session.execute(
        select(Evento)
        .options(joinedload(Evento.acao))
        .order_by(Evento.data_evento.desc())
        .offset(offset)
        .limit(limit)
    )
    items: list[dict[str, Any]] = []
    for evento in result.unique().scalars():
        acao_nome = _resolve_timeline_acao_nome(evento.acao, evento.acao_id)
        items.append(
            {
                "id": evento.id,
                "tipo": "evento",
                "data": evento.data_evento.isoformat(),
                "acao_id": evento.acao_id,
                "acao_nome": acao_nome,
                "titulo": (f"[{evento.tipo}] {acao_nome}"),
                "descricao": evento.descricao,
                "detalhes": EventoBase.model_validate(evento),
            }
        )
    return items


async def _load_changes_page(
    session: AsyncSession,
    offset: int,
    limit: int,
) -> list[dict[str, Any]]:
    """Load status changes with SQL-level pagination.

    Uses ``joinedload`` to fetch the associated action in the same query,
    avoiding a full scan of the actions table per request.
    """
    result = await session.execute(
        select(AuditLog)
        .options(joinedload(AuditLog.acao))
        .order_by(AuditLog.data_criacao.desc())
        .offset(offset)
        .limit(limit)
    )
    items: list[dict[str, Any]] = []
    for change in result.unique().scalars():
        status_anterior = change.status_anterior.value if change.status_anterior else None
        status_novo = change.status_novo.value
        acao_nome = _resolve_timeline_acao_nome(change.acao, change.acao_id)
        items.append(
            {
                "id": change.id,
                "tipo": "status_change",
                "data": change.data_criacao.isoformat(),
                "acao_id": change.acao_id,
                "acao_nome": acao_nome,
                "titulo": (f"Status alterado: {acao_nome}"),
                "descricao": f"De {status_anterior} para {status_novo}",
                "detalhes": StatusChangeBase.model_validate(change),
            }
        )
    return items


@router.get("", response_model=TimelineListResponse | ErrorResponse)
@limiter.limit(RATE_LIMIT_PUBLIC_READ)
async def get_timeline(
    request: Request,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=200),
    tipo: str | None = Query(default=None, description="Filtrar por tipo: evento, status_change"),
    session: AsyncSession = Depends(get_db),
) -> TimelineListResponse | ErrorResponse:
    """Obter timeline combinado.

    Retorna uma lista cronológica combinando eventos e mudanças de status.

    Parâmetros:
    - page: Número da página (padrão: 1)
    - page_size: Itens por página (padrão: 50, máximo: 200)
    - tipo: Filtrar por tipo (evento, status_change)
    """
    try:
        offset = (page - 1) * page_size

        if tipo == "evento":
            count_result = await session.execute(select(func.count()).select_from(Evento))
            total = count_result.scalar() or 0
            if total == 0:
                return TimelineListResponse(data=[], total=0)
            items = await _load_eventos_page(session, offset, page_size)
            return TimelineListResponse(
                data=[TimelineItem(**item) for item in items],
                total=total,
            )

        if tipo == "status_change":
            count_result = await session.execute(select(func.count()).select_from(AuditLog))
            total = count_result.scalar() or 0
            if total == 0:
                return TimelineListResponse(data=[], total=0)
            items = await _load_changes_page(session, offset, page_size)
            return TimelineListResponse(
                data=[TimelineItem(**item) for item in items],
                total=total,
            )

        count_e = (await session.execute(select(func.count()).select_from(Evento))).scalar() or 0
        count_c = (await session.execute(select(func.count()).select_from(AuditLog))).scalar() or 0
        total = count_e + count_c

        if total == 0:
            return TimelineListResponse(data=[], total=0)

        sql_limit = offset + page_size
        eventos_items = await _load_eventos_page(session, 0, sql_limit)
        changes_items = await _load_changes_page(session, 0, sql_limit)

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
        logger.error("Erro ao obter timeline", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=ErrorDetail(
                message="Erro interno do servidor",
                code="INTERNAL_ERROR",
            ).model_dump(),
        )


# ============================================================================
# Endpoints para timeline de ação específica
# ============================================================================


@acao_timeline_router.get(
    "/{acao_id}/timeline",
    response_model=TimelineListResponse | ErrorResponse,
    tags=["timeline"],
)
@limiter.limit(RATE_LIMIT_PUBLIC_READ)
async def get_acao_timeline(
    request: Request,
    acao_id: str,
    page: int = Query(default=1, ge=1, description="Número da página"),
    page_size: int = Query(default=20, ge=1, le=100, description="Itens por página"),
    tipo: str | None = Query(default=None, description="Filtrar por tipo: evento, status_change"),
    session: AsyncSession = Depends(get_db),
) -> TimelineListResponse | ErrorResponse:
    """Obter timeline para uma ação específica.

    Retorna uma lista cronológica de eventos e mudanças de status para uma ação.

    Args:
        acao_id: ID da ação
        page: Número da página (padrão: 1)
        page_size: Itens por página (padrão: 20, máximo: 100)
        tipo: Filtrar por tipo (evento, status_change)

    Returns:
        TimelineListResponse com itens de timeline para a ação
    """
    try:
        # Verificar se existe pelo menos um registro para esta ação
        count_result = await session.execute(
            select(func.count()).select_from(
                select(Evento.acao_id)
                .where(Evento.acao_id == acao_id)
                .union_all(select(AuditLog.acao_id).where(AuditLog.acao_id == acao_id))
                .alias()
            )
        )
        total_records = count_result.scalar() or 0

        if total_records == 0:
            raise HTTPException(
                status_code=404,
                detail=f"Nenhum registro de timeline encontrado para ação: {acao_id}",
            )

        offset = (page - 1) * page_size

        eventos_result = await session.execute(
            select(Evento)
            .where(Evento.acao_id == acao_id)
            .order_by(Evento.data_evento.desc())
            .offset(offset)
            .limit(page_size)
        )
        eventos = eventos_result.scalars().all()

        changes_result = await session.execute(
            select(AuditLog)
            .where(AuditLog.acao_id == acao_id)
            .order_by(AuditLog.data_criacao.desc())
            .offset(offset)
            .limit(page_size)
        )
        changes = changes_result.scalars().all()

        acao_nome_result = await session.execute(select(Acao.nome).where(Acao.id == acao_id))
        acao_nome = acao_nome_result.scalar_one_or_none() or f"Ação {acao_id}"

        timeline_items: list[dict[str, Any]] = []

        for evento in eventos:
            timeline_items.append(
                {
                    "id": evento.id,
                    "tipo": "evento",
                    "data": evento.data_evento.isoformat(),
                    "acao_id": evento.acao_id,
                    "acao_nome": acao_nome,
                    "titulo": (f"[{evento.tipo}] {acao_nome}"),
                    "descricao": evento.descricao,
                    "detalhes": EventoBase.model_validate(evento),
                }
            )

        for change in changes:
            status_anterior = change.status_anterior.value if change.status_anterior else None
            status_novo = change.status_novo.value
            timeline_items.append(
                {
                    "id": change.id,
                    "tipo": "status_change",
                    "data": change.data_criacao.isoformat(),
                    "acao_id": change.acao_id,
                    "acao_nome": acao_nome,
                    "titulo": (f"Status alterado: {acao_nome}"),
                    "descricao": f"De {status_anterior} para {status_novo}",
                    "detalhes": StatusChangeBase.model_validate(change),
                }
            )

        timeline_items.sort(key=lambda x: cast("str", x["data"]), reverse=True)

        if tipo:
            timeline_items = [item for item in timeline_items if item["tipo"] == tipo]

        total = len(timeline_items)
        offset = (page - 1) * page_size
        paginated_items = timeline_items[offset : offset + page_size]

        return TimelineListResponse(
            data=[TimelineItem(**item) for item in paginated_items],
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
