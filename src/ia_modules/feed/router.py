"""IA Brasil — Feed Router.

Endpoints para consulta de feed público de atividades:
- GET /feed - Listar atividades do feed
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from loguru import logger
from pydantic import BaseModel
from sqlalchemy import String, cast, func, literal_column, select, union_all

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator

    from sqlalchemy.ext.asyncio import AsyncSession

from src.core.db import (
    Acao,
    AuditLog,
    Avaliacao,
    Evento,
    Evidencia,
    Fonte,
    get_session,
)
from src.core.limiter import RATE_LIMIT_PUBLIC_READ, limiter
from src.core.pii import log_evidence_access, redact_pii
from src.modules.public_portal.schemas import ErrorDetail, ErrorResponse

router = APIRouter(prefix="/feed")

# ============================================================================
# Schemas
# ============================================================================


class FeedItemBase(BaseModel):
    """Schema base para item de feed."""

    model_config = {"from_attributes": True}

    id: str
    tipo: str  # 'evento', 'status_change', 'evidencia', 'avaliacao'
    titulo: str
    descricao: str
    data: str
    acao_id: str | None = None
    acao_nome: str | None = None
    fonte_url: str | None = None
    tags: list[str] = []


class FeedListResponse(BaseModel):
    """Resposta para listagem de feed."""

    data: list[FeedItemBase]
    total: int
    page: int
    page_size: int
    pages: int


# ============================================================================
# Utilitários
# ============================================================================


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """Dependency para obter sessão do banco."""
    async with get_session() as session:
        yield session


def extract_tags_from_text(text: str) -> list[str]:
    """Extrair tags de um texto com base em palavras-chave."""
    tags_map = {
        "anuncio": ["anúncio", "anunciado", "divulgado"],
        "investimento": ["investimento", "recurso", "financiamento"],
        "infraestrutura": ["infraestrutura", "centro", "laboratório", "lab"],
        "inovação": ["inovação", "inovador", "tecnologia"],
        "entrega": ["entregue", "concluído", "finalizado"],
        "progresso": ["progresso", "avanço", "evolução"],
        "financeiro": ["financeiro", "orçamento", "recurso"],
        "pesquisa": ["pesquisa", "estudo", "investigação"],
        "tecnologia": ["tecnologia", "digital", "plataforma"],
        "lançamento": ["lançamento", "lançado", "inaugurado"],
        "contratacao": ["contratação", "contratado", "assinado"],
        "revisao": ["revisão", "atualização", "avaliação"],
        "suspensao": ["suspensão", "pausa", "interrupção"],
    }

    text_lower = text.lower()
    found_tags = []

    for tag, keywords in tags_map.items():
        if any(keyword in text_lower for keyword in keywords):
            found_tags.append(tag)

    return list(set(found_tags))  # Remover duplicatas


# ============================================================================
# Endpoints
# ============================================================================


def _resolve_acao_nome(acao_id: str | None, acoes_map: dict[str, str]) -> str | None:
    """Resolve o nome de exibição de uma ação a partir do mapa de ações.

    Eventos de nível de plano (acao_id vazio) são rotulados como 'Plano PBIA'
    em vez de exibir uma mensagem de 'não encontrada'.
    """
    if not acao_id:
        return "Plano PBIA"
    return acoes_map.get(acao_id, f"Ação não encontrada (ID: {acao_id})")


async def _load_eventos(
    session: AsyncSession,
    offset: int,
    limit: int,
    acoes_map: dict[str, str] | None = None,
) -> list[dict[str, Any]]:
    """Load eventos with pagination.

    Uses acoes_map to populate acao_nome without extra queries.
    If acoes_map is not provided, loads it in a single query.
    """
    # Load acoes_map if not provided
    if acoes_map is None:
        acoes_result = await session.execute(select(Acao.id, Acao.nome))
        acoes_map = {row[0]: row[1] for row in acoes_result}

    result = await session.execute(
        select(Evento).order_by(Evento.data_evento.desc()).offset(offset).limit(limit)
    )
    items: list[dict[str, Any]] = []
    for evento in result.unique().scalars():
        acao_nome = _resolve_acao_nome(evento.acao_id, acoes_map)
        tipo_val = evento.tipo.value if hasattr(evento.tipo, "value") else str(evento.tipo)
        descricao = redact_pii(evento.descricao)
        items.append(
            {
                "id": f"event-{evento.id}",
                "tipo": "evento",
                "titulo": (f"[{tipo_val}] {acao_nome}"),
                "descricao": descricao,
                "data": evento.data_evento.isoformat(),
                "acao_id": evento.acao_id,
                "acao_nome": acao_nome,
                "fonte_url": evento.fonte_url,
                "tags": extract_tags_from_text(descricao),
            }
        )
    return items


async def _load_changes(
    session: AsyncSession,
    offset: int,
    limit: int,
    acoes_map: dict[str, str] | None = None,
) -> list[dict[str, Any]]:
    """Load status changes with pagination.

    Uses acoes_map to populate acao_nome without extra queries.
    If acoes_map is not provided, loads it in a single query.
    """
    # Load acoes_map if not provided
    if acoes_map is None:
        acoes_result = await session.execute(select(Acao.id, Acao.nome))
        acoes_map = {row[0]: row[1] for row in acoes_result}

    result = await session.execute(
        select(AuditLog).order_by(AuditLog.data_criacao.desc()).offset(offset).limit(limit)
    )
    items: list[dict[str, Any]] = []
    for change in result.unique().scalars():
        status_anterior = change.status_anterior.value if change.status_anterior else "Não iniciado"
        status_novo = change.status_novo.value
        acao_nome = _resolve_acao_nome(change.acao_id, acoes_map)
        justificativa = redact_pii(change.justificativa)
        items.append(
            {
                "id": f"status-{change.id}",
                "tipo": "status_change",
                "titulo": (f"Status alterado: {acao_nome}"),
                "descricao": (
                    f"Mudança de status: {status_anterior} → {status_novo}. {justificativa}"
                ),
                "data": change.data_criacao.isoformat(),
                "acao_id": change.acao_id,
                "acao_nome": acao_nome,
                "fonte_url": None,
                "tags": [
                    *extract_tags_from_text(justificativa),
                    "progresso",
                ],
            }
        )
    return items


async def _load_evidencias(
    session: AsyncSession,
    offset: int,
    limit: int,
) -> list[dict[str, Any]]:
    """Load evidencias with pagination."""
    result = await session.execute(
        select(Evidencia, Fonte)
        .join(Fonte, Evidencia.fonte_id == Fonte.id)
        .order_by(Evidencia.data_evidencia.desc())
        .offset(offset)
        .limit(limit)
    )
    items: list[dict[str, Any]] = []
    for ev_row in result:
        evidencia = ev_row[0]
        fonte = ev_row[1]
        data_str = (
            evidencia.data_evidencia.isoformat()
            if evidencia.data_evidencia
            else fonte.data_coleta.isoformat()
        )
        ev_tipo = evidencia.tipo.value
        resumo_redigido = redact_pii(evidencia.resumo or "")
        log_evidence_access(evidencia.id, "GET /api/v1/feed")
        items.append(
            {
                "id": f"evidencia-{evidencia.id}",
                "tipo": "evidencia",
                "titulo": (f"Nova evidência: {ev_tipo}"),
                "descricao": (resumo_redigido or "Evidência adicionada ao sistema"),
                "data": data_str,
                "acao_id": None,
                "acao_nome": None,
                "fonte_url": fonte.url,
                "tags": [
                    *extract_tags_from_text(resumo_redigido),
                    "evidencia",
                    ev_tipo,
                ],
            }
        )
    return items


async def _load_avaliacoes(
    session: AsyncSession,
    offset: int,
    limit: int,
    acoes_map: dict[str, str] | None = None,
) -> list[dict[str, Any]]:
    """Load avaliacoes with pagination.

    Uses acoes_map to populate acao_nome without extra queries.
    If acoes_map is not provided, loads it in a single query.
    """
    # Load acoes_map if not provided
    if acoes_map is None:
        acoes_result = await session.execute(select(Acao.id, Acao.nome))
        acoes_map = {row[0]: row[1] for row in acoes_result}

    result = await session.execute(
        select(Avaliacao).order_by(Avaliacao.data_avaliacao.desc()).offset(offset).limit(limit)
    )
    items: list[dict[str, Any]] = []
    for avaliacao in result.unique().scalars():
        acao_nome = _resolve_acao_nome(avaliacao.acao_id, acoes_map)
        justificativa = redact_pii(avaliacao.justificativa)
        items.append(
            {
                "id": f"avaliacao-{avaliacao.id}",
                "tipo": "avaliacao",
                "titulo": (f"Nova avaliação: {acao_nome}"),
                "descricao": (
                    f"Status avaliado: {avaliacao.status_avaliado.value}. {justificativa}"
                ),
                "data": avaliacao.data_avaliacao.isoformat(),
                "acao_id": avaliacao.acao_id,
                "acao_nome": acao_nome,
                "fonte_url": None,
                "tags": [
                    *extract_tags_from_text(justificativa),
                    "avaliacao",
                ],
            }
        )
    return items


async def _load_unified_feed(
    session: AsyncSession,
    acoes_map: dict[str, str],
    offset: int,
    limit: int,
) -> list[dict[str, Any]]:
    """Load all feed types in a single UNION ALL query.

    Replaces the previous approach of loading from 4 separate tables
    and merging in Python, which caused excessive memory usage.
    """
    evento_subq = (
        select(
            Evento.id.label("raw_id"),
            literal_column("'evento'").label("tipo"),
            Evento.descricao.label("descricao"),
            Evento.data_evento.label("data"),
            Evento.acao_id.label("acao_id"),
            Evento.fonte_url.label("fonte_url"),
            cast(Evento.tipo, String).label("campo_a"),
            literal_column("NULL").label("campo_b"),
        )
    ).subquery("ev_union")

    audit_subq = (
        select(
            AuditLog.id.label("raw_id"),
            literal_column("'status_change'").label("tipo"),
            AuditLog.justificativa.label("descricao"),
            AuditLog.data_criacao.label("data"),
            AuditLog.acao_id.label("acao_id"),
            literal_column("NULL").label("fonte_url"),
            cast(AuditLog.status_anterior, String).label("campo_a"),
            cast(AuditLog.status_novo, String).label("campo_b"),
        )
    ).subquery("al_union")

    evidencia_subq = (
        select(
            Evidencia.id.label("raw_id"),
            literal_column("'evidencia'").label("tipo"),
            Evidencia.resumo.label("descricao"),
            func.coalesce(Evidencia.data_evidencia, Fonte.data_coleta).label("data"),
            literal_column("NULL").label("acao_id"),
            Fonte.url.label("fonte_url"),
            cast(Evidencia.tipo, String).label("campo_a"),
            literal_column("NULL").label("campo_b"),
        ).join(Fonte, Evidencia.fonte_id == Fonte.id)
    ).subquery("evi_union")

    avaliacao_subq = (
        select(
            Avaliacao.id.label("raw_id"),
            literal_column("'avaliacao'").label("tipo"),
            Avaliacao.justificativa.label("descricao"),
            Avaliacao.data_avaliacao.label("data"),
            Avaliacao.acao_id.label("acao_id"),
            literal_column("NULL").label("fonte_url"),
            cast(Avaliacao.status_avaliado, String).label("campo_a"),
            literal_column("NULL").label("campo_b"),
        )
    ).subquery("av_union")

    union_q = union_all(
        select(evento_subq),
        select(audit_subq),
        select(evidencia_subq),
        select(avaliacao_subq),
    ).subquery("feed_union")

    final_q = select(union_q).order_by(union_q.c.data.desc()).limit(limit).offset(offset)

    result = await session.execute(final_q)

    items: list[dict[str, Any]] = []
    for row in result:
        tipo = row.tipo
        raw_id = row.raw_id
        descricao = redact_pii(row.descricao or "")
        data = row.data
        acao_id = row.acao_id
        fonte_url = row.fonte_url
        campo_a = row.campo_a
        campo_b = row.campo_b

        if tipo == "evento":
            acao_nome = _resolve_acao_nome(acao_id, acoes_map)
            items.append(
                {
                    "id": f"event-{raw_id}",
                    "tipo": "evento",
                    "titulo": f"[{campo_a}] {acao_nome}",
                    "descricao": descricao,
                    "data": data.isoformat(),
                    "acao_id": acao_id,
                    "acao_nome": acao_nome,
                    "fonte_url": fonte_url,
                    "tags": extract_tags_from_text(descricao),
                }
            )
        elif tipo == "status_change":
            status_anterior = campo_a if campo_a else "Não iniciado"
            status_novo = campo_b
            acao_nome = _resolve_acao_nome(acao_id, acoes_map)
            items.append(
                {
                    "id": f"status-{raw_id}",
                    "tipo": "status_change",
                    "titulo": f"Status alterado: {acao_nome}",
                    "descricao": (
                        f"Mudança de status: {status_anterior} → {status_novo}. {descricao}"
                    ),
                    "data": data.isoformat(),
                    "acao_id": acao_id,
                    "acao_nome": acao_nome,
                    "fonte_url": None,
                    "tags": [
                        *extract_tags_from_text(descricao),
                        "progresso",
                    ],
                }
            )
        elif tipo == "evidencia":
            log_evidence_access(raw_id, "GET /api/v1/feed")
            items.append(
                {
                    "id": f"evidencia-{raw_id}",
                    "tipo": "evidencia",
                    "titulo": f"Nova evidência: {campo_a}",
                    "descricao": descricao or "Evidência adicionada ao sistema",
                    "data": data.isoformat(),
                    "acao_id": None,
                    "acao_nome": None,
                    "fonte_url": fonte_url,
                    "tags": [
                        *extract_tags_from_text(descricao or ""),
                        "evidencia",
                        campo_a,
                    ],
                }
            )
        elif tipo == "avaliacao":
            acao_nome = _resolve_acao_nome(acao_id, acoes_map)
            items.append(
                {
                    "id": f"avaliacao-{raw_id}",
                    "tipo": "avaliacao",
                    "titulo": f"Nova avaliação: {acao_nome}",
                    "descricao": f"Status avaliado: {campo_a}. {descricao}",
                    "data": data.isoformat(),
                    "acao_id": acao_id,
                    "acao_nome": acao_nome,
                    "fonte_url": None,
                    "tags": [
                        *extract_tags_from_text(descricao),
                        "avaliacao",
                    ],
                }
            )

    return items


@router.get("", response_model=FeedListResponse | ErrorResponse)
@limiter.limit(RATE_LIMIT_PUBLIC_READ)
async def get_feed(
    request: Request,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=200),
    tipo: str | None = Query(
        default=None,
        description=("Filtrar por tipo: evento, status_change, evidencia, avaliacao"),
    ),
    session: AsyncSession = Depends(get_db),
) -> FeedListResponse | ErrorResponse:
    """Obter feed público de atividades.

    Retorna uma lista cronológica de todas as atividades
    relacionadas ao monitoramento do PBIA.

    Parâmetros:
    - page: Número da página (padrão: 1)
    - page_size: Itens por página (padrão: 50, máximo: 200)
    - tipo: Filtrar por tipo de atividade
    """
    try:
        # Contar totais por tipo via SQL
        count_eventos = (
            await session.execute(select(func.count()).select_from(Evento))
        ).scalar() or 0
        count_changes = (
            await session.execute(select(func.count()).select_from(AuditLog))
        ).scalar() or 0
        count_evidencias = (
            await session.execute(select(func.count()).select_from(Evidencia))
        ).scalar() or 0
        count_avaliacoes = (
            await session.execute(select(func.count()).select_from(Avaliacao))
        ).scalar() or 0

        # Aplicar filtro por tipo nos counts
        type_counts: dict[str, int] = {
            "evento": count_eventos,
            "status_change": count_changes,
            "evidencia": count_evidencias,
            "avaliacao": count_avaliacoes,
        }
        if tipo:
            total = type_counts.get(tipo, 0)
        else:
            total = count_eventos + count_changes + count_evidencias + count_avaliacoes

        # Carregar ações para referência (apenas IDs e nomes)
        acoes_result = await session.execute(select(Acao.id, Acao.nome))
        acoes_map: dict[str, str] = {row[0]: row[1] for row in acoes_result}

        offset = (page - 1) * page_size
        feed_items: list[dict[str, Any]] = []

        if tipo is not None:
            loaders = {
                "evento": lambda: _load_eventos(session, offset, page_size, acoes_map),
                "status_change": lambda: _load_changes(
                    session,
                    offset,
                    page_size,
                    acoes_map,
                ),
                "evidencia": lambda: _load_evidencias(
                    session,
                    offset,
                    page_size,
                ),
                "avaliacao": lambda: _load_avaliacoes(
                    session,
                    offset,
                    page_size,
                    acoes_map,
                ),
            }
            loader = loaders.get(tipo)
            if loader:
                feed_items = await loader()
        else:
            feed_items = await _load_unified_feed(
                session,
                acoes_map,
                offset,
                page_size,
            )

        paginated_items = feed_items

        return FeedListResponse(
            data=[FeedItemBase(**item) for item in paginated_items],
            total=total,
            page=page,
            page_size=page_size,
            pages=((total + page_size - 1) // page_size if total > 0 else 0),
        )
    except HTTPException:
        raise
    except Exception:
        logger.error("Erro ao obter feed", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=ErrorDetail(
                message="Erro interno do servidor",
                code="INTERNAL_ERROR",
            ).model_dump(),
        )
