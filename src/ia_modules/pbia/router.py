"""IA Brasil — PBIA Search Router.

Endpoint: GET /api/v1/pbia/search?q=query
Full-text search em ações (LIKE para SQLite, FTS para PostgreSQL via migração futura).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from fastapi import APIRouter, Depends, Query, Request
from loguru import logger
from pydantic import BaseModel, Field
from sqlalchemy import func, or_, select

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator

    from sqlalchemy.ext.asyncio import AsyncSession

from src.core.db import Acao, Indicador, Meta, StatusAcao, get_session
from src.core.limiter import RATE_LIMIT_PUBLIC_READ, limiter
from src.core.pii import redact_pii

router = APIRouter(prefix="/pbia", tags=["pbia"])


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """Dependency for database session."""
    async with get_session() as session:
        yield session


class SearchResult(BaseModel):
    """Schema for search result."""

    id: str = Field(..., description="Ação ID")
    nome: str = Field(..., description="Nome da ação")
    descricao: str | None = Field(None, description="Descrição da ação")
    trecho_original: str | None = Field(None, description="Trecho original do PBIA")
    programa: str | None = Field(None, description="Nome do programa")
    rank: float = Field(..., description="Ranking de relevância")


class SearchResponse(BaseModel):
    """Schema for search response."""

    query: str
    total: int
    results: list[SearchResult]


def _calculate_rank(
    nome: str | None, descricao: str | None, trecho: str | None, query: str
) -> float:
    """Calcula ranking simples baseado em ocorrências da query."""
    rank = 0.0
    q_lower = query.lower()
    if nome and q_lower in nome.lower():
        rank += 1.0
    if descricao and q_lower in descricao.lower():
        rank += 0.7
    if trecho and q_lower in trecho.lower():
        rank += 0.5
    return rank


def _is_postgres(session: AsyncSession) -> bool:
    """Verifica se o banco é PostgreSQL (vs SQLite) via dialect name."""
    dialect = session.bind.dialect.name if session.bind else "sqlite"
    return dialect == "postgresql"


@router.get("/search", response_model=SearchResponse)
@limiter.limit(RATE_LIMIT_PUBLIC_READ)
async def search_acoes(
    request: Request,
    q: str = Query(..., min_length=2, description="Termo de busca"),
    limit: int = Query(default=20, ge=1, le=100),
    session: AsyncSession = Depends(get_db),
) -> SearchResponse:
    """Busca textual em ações do PBIA.

    Usa PostgreSQL FTS (tsvector/tsquery) quando disponível,
    com fallback para ILIKE (SQLite).
    Pesquisa em nome, descrição e trecho_original.
    """
    logger.info(f"FTS search query: {q}")

    is_pg = _is_postgres(session)

    if is_pg:
        # PostgreSQL FTS
        tsquery = func.plainto_tsquery("portuguese", q)
        tsvector_nome = func.to_tsvector("portuguese", Acao.nome)
        tsvector_desc = func.to_tsvector("portuguese", Acao.descricao)
        tsvector_trecho = func.to_tsvector("portuguese", Acao.trecho_original)

        rank_nome = func.ts_rank(tsvector_nome, tsquery)
        rank_desc = func.ts_rank(tsvector_desc, tsquery)
        rank_trecho = func.ts_rank(tsvector_trecho, tsquery)
        rank_total = rank_nome + rank_desc + rank_trecho

        stmt = (
            select(Acao, rank_total.label("rank"))
            .where(
                or_(
                    tsvector_nome.op("@@")(tsquery),
                    tsvector_desc.op("@@")(tsquery),
                    tsvector_trecho.op("@@")(tsquery),
                )
            )
            .order_by(rank_total.desc())
            .limit(limit)
        )

        result = await session.execute(stmt)
        rows = result.all()
        acoes = [row[0] for row in rows]
        ranks = {row[0].id: float(row[1]) for row in rows}
    else:
        # SQLite fallback: ILIKE
        search_pattern = f"%{q}%"
        stmt = (
            select(Acao)
            .where(
                or_(
                    Acao.nome.ilike(search_pattern),
                    Acao.descricao.ilike(search_pattern),
                    Acao.trecho_original.ilike(search_pattern),
                )
            )
            .limit(limit)
        )
        result = await session.execute(stmt)
        acoes = list(result.scalars())
        ranks = {}

    results = [
        SearchResult(
            id=acao.id,
            nome=acao.nome,
            descricao=redact_pii(acao.descricao) if acao.descricao else None,
            trecho_original=redact_pii(acao.trecho_original) if acao.trecho_original else None,
            programa=None,
            rank=ranks.get(
                acao.id,
                _calculate_rank(acao.nome, acao.descricao, acao.trecho_original, q),
            ),
        )
        for acao in acoes
    ]

    return SearchResponse(query=q, total=len(results), results=results)


# Dashboard schemas
class DashboardIndicador(BaseModel):
    """Schema for dashboard indicator."""

    id: str
    nome: str
    tipo: str
    linha_base: float | None = None
    meta_valor: float | None = None
    unidade: str | None = None


class DashboardMetrica(BaseModel):
    """Schema for dashboard metric."""

    id: str
    nome: str
    valor: float
    unidade: str
    descricao: str


class DashboardStatusSummary(BaseModel):
    """Schema for status summary."""

    status: str
    count: int
    percentage: float


class DashboardResponse(BaseModel):
    """Schema for dashboard response."""

    indicadores: list[DashboardIndicador]
    metricas: list[DashboardMetrica]
    status_summary: list[DashboardStatusSummary]


@router.get("/dashboard", response_model=DashboardResponse)
@limiter.limit(RATE_LIMIT_PUBLIC_READ)
async def get_dashboard(
    request: Request,
    session: AsyncSession = Depends(get_db),
) -> DashboardResponse:
    """Retorna dados do dashboard com indicadores e métricas reais do PBIA."""
    from src.core.db import Acao

    # Get indicadores
    stmt = select(Indicador, Meta).join(Meta).limit(20)
    result = await session.execute(stmt)
    indicadores_raw = result.scalars().all()

    indicadores = [
        DashboardIndicador(
            id=str(i.id),
            nome=i.nome,
            tipo=i.tipo.value if i.tipo else "resultado",
            linha_base=float(i.linha_base) if i.linha_base else None,
            meta_valor=float(i.meta_valor) if i.meta_valor else None,
            unidade=i.unidade,
        )
        for i in indicadores_raw
    ]

    # Get status summary
    status_stmt = select(Acao.status, func.count(Acao.id)).select_from(Acao).group_by(Acao.status)
    result = await session.execute(status_stmt)
    status_counts = {str(row[0]): row[1] for row in result.fetchall()}

    total_acoes = sum(status_counts.values())
    status_summary = [
        DashboardStatusSummary(
            status=status_str,
            count=count,
            percentage=round(count / total_acoes * 100, 1) if total_acoes > 0 else 0,
        )
        for status_str, count in status_counts.items()
    ]

    # Get metrics
    acoes_total = await session.scalar(select(func.count()).select_from(Acao))
    acoes_entregues = await session.scalar(
        select(func.count()).select_from(Acao).where(Acao.status == StatusAcao.entregue)
    )

    metricas = [
        DashboardMetrica(
            id="met-1",
            nome="Total Ações",
            valor=float(acoes_total or 0),
            unidade="",
            descricao="Ações previstas no PBIA",
        ),
        DashboardMetrica(
            id="met-3",
            nome="Ações Entregues",
            valor=float(acoes_entregues or 0),
            unidade="",
            descricao="Ações com status entregue",
        ),
        DashboardMetrica(
            id="met-6",
            nome="Progresso Geral",
            valor=round((float(acoes_entregues or 0) / float(acoes_total or 1)) * 100, 1),
            unidade="%",
            descricao="Média de progresso",
        ),
    ]

    return DashboardResponse(
        indicadores=indicadores,
        metricas=metricas,
        status_summary=status_summary,
    )
