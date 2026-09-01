"""IA Brasil — Public Portal Router.

Endpoints de leitura pública para consulta do PBIA:
- GET /eixos - Listar eixos
- GET /eixos/{id} - Obter eixo por ID
- GET /programas - Listar programas
- GET /programas/{id} - Obter programa por ID
- GET /acoes - Listar ações
- GET /acoes/{id} - Obter ação por ID (com detalhes)
"""

from __future__ import annotations

import base64
import hashlib
import json
from datetime import date, datetime, timedelta
from typing import TYPE_CHECKING, Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from loguru import logger
from pydantic import BaseModel, Field
from sqlalchemy import and_, func, or_, select
from sqlalchemy.orm import joinedload

from src.core.limiter import RATE_LIMIT_PUBLIC_READ, limiter

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator

    from sqlalchemy.ext.asyncio import AsyncSession
from src.core.db import (
    Acao,
    AcaoInstituicao,
    AuditLog,
    Eixo,
    Evento,
    ExecucaoFinanceira,
    Indicador,
    IndicadorResultado,
    IngestionRun,
    Instituicao,
    Meta,
    Plano,
    Programa,
    Recurso,
    StatusAcao,
    get_session,
)
from src.modules.public_portal.constants import (
    CODE_INTERNAL_ERROR,
    CODE_NOT_FOUND,
    DASHBOARD_INDICADORES_LIMIT,
    DAYS_PER_YEAR,
    DEFAULT_PAGE,
    DEFAULT_PAGE_SIZE,
    MAX_PAGE_SIZE,
    METRIC_DESC_ENTREGUES,
    METRIC_DESC_INICIADAS,
    METRIC_DESC_INVESTIMENTO,
    METRIC_DESC_PRAZO,
    METRIC_DESC_PROGRESSO,
    METRIC_DESC_TOTAL,
    METRIC_ID_ENTREGUES,
    METRIC_ID_INICIADAS,
    METRIC_ID_INVESTIMENTO,
    METRIC_ID_PRAZO,
    METRIC_ID_PROGRESSO,
    METRIC_ID_TOTAL,
    METRIC_NAME_ENTREGUES,
    METRIC_NAME_INICIADAS,
    METRIC_NAME_INVESTIMENTO,
    METRIC_NAME_PRAZO,
    METRIC_NAME_PROGRESSO,
    METRIC_NAME_TOTAL,
    MSG_ACAO_PREFIX,
    MSG_ERRO_INTERNO,
    MSG_NENHUM_PLANO,
    MSG_PREFIX_ACAO,
    MSG_PREFIX_EIXO,
    MSG_PREFIX_PLANO,
    MSG_PREFIX_PROGRAMA,
    PERCENTAGE_MULTIPLIER,
    UNIDADE_ACOES,
    UNIDADE_MOEDA,
    UNIDADE_PERCENTUAL,
    UNIDADE_TEMPO,
)
from src.modules.public_portal.schemas import (
    AcaoBase,
    AcaoDetail,
    AcaoInstituicaoBase,
    AcaoListResponse,
    EixoBase,
    EixoDetail,
    EixoListResponse,
    ErrorDetail,
    ErrorResponse,
    IndicadorBase,
    InstituicaoBase,
    MetaBase,
    PlanoDetail,
    ProgramaBase,
    ProgramaDetail,
    ProgramaListResponse,
    RecursoBase,
)

router = APIRouter(prefix="/pbia")

# ============================================================================
# Utilitários
# ============================================================================


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """Dependency para obter sessão do banco."""
    async with get_session() as session:
        yield session


# ============================================================================
# Utilitários — ETag (RFC 9110) e paginação por cursor
# ============================================================================


def _etag_for_payload(payload: BaseModel) -> str:
    """ETag forte (SHA-256) a partir do JSON serializado do payload.

    A digest é determinística para o mesmo conteúdo — clientes a devolvem
    em ``If-None-Match`` e o servidor responde 304 quando nada mudou.

    Args:
        payload: Modelo de resposta (sucesso) a ser hasheado.

    Returns:
        ETag entre aspas (ex.: ``"9f86d081..."``), conforme RFC 9110.
    """
    raw = json.dumps(
        payload.model_dump(mode="json"),
        sort_keys=True,
        ensure_ascii=False,
        separators=(",", ":"),
    )
    digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()
    return f'"{digest}"'


def _maybe_not_modified(
    request: Request,
    response: Response,
    etag: str,
) -> Response | None:
    """Responde 304 quando ``If-None-Match`` casa; senão anexa o header ``ETag``.

    Args:
        request: Request atual (lê ``If-None-Match``).
        response: Response injetada pelo FastAPI (recebe o header ``ETag``).
        etag: Valor de ETag da representação atual.

    Returns:
        ``Response`` 304 (vazia) quando o cliente já possui a versão;
        ``None`` caso contrário — o endpoint deve retornar o payload,
        já com o header ``ETag`` anexado via ``response``.
    """
    if_none_match = request.headers.get("if-none-match")
    if if_none_match is not None and etag in if_none_match:
        return Response(status_code=304, headers={"ETag": etag})
    response.headers["ETag"] = etag
    return None


def _encode_cursor(nome: str, id_: str) -> str:
    """Codifica a âncora de paginação (nome, id) como cursor opaco.

    Args:
        nome: Último ``nome`` da página corrente (chave de ordenação).
        id_: Último ``id`` da página corrente (desempate determinístico).

    Returns:
        String base64url (sem padding) com o JSON da âncora.
    """
    raw = json.dumps(
        {"nome": nome, "id": id_},
        ensure_ascii=False,
        separators=(",", ":"),
    )
    return base64.urlsafe_b64encode(raw.encode("utf-8")).decode("ascii").rstrip("=")


def _decode_cursor(cursor: str) -> tuple[str, str]:
    """Decodifica um cursor opaco de volta para a âncora (nome, id).

    Args:
        cursor: Cursor produzido por :func:`_encode_cursor`.

    Returns:
        Tupla ``(nome, id)`` da âncora.

    Raises:
        HTTPException: 400 quando o cursor é inválido/malformado.
    """
    try:
        raw = base64.urlsafe_b64decode(cursor.encode("ascii") + b"=" * (-len(cursor) % 4))
        data = json.loads(raw.decode("utf-8"))
    except Exception:
        raise HTTPException(status_code=400, detail="Cursor de paginação inválido")
    if not isinstance(data, dict):
        raise HTTPException(status_code=400, detail="Cursor de paginação inválido")
    nome = data.get("nome")
    id_ = data.get("id")
    if not isinstance(nome, str) or not isinstance(id_, str):
        raise HTTPException(status_code=400, detail="Cursor de paginação inválido")
    return nome, id_


# Pagination defaults, dashboard metrics, and other constants are now defined in constants.py

# ============================================================================
# Endpoints - Plano
# ============================================================================


@router.get("/planos", response_model=PlanoDetail | ErrorResponse)
@limiter.limit(RATE_LIMIT_PUBLIC_READ)
async def list_planos(
    request: Request,
    session: AsyncSession = Depends(get_db),
) -> PlanoDetail | ErrorResponse:
    """Listar todos os planos.

    Retorna uma lista de todos os planos do PBIA.
    """
    try:
        result = await session.execute(select(Plano))
        plano = result.scalar_one()
        if not plano:
            raise HTTPException(status_code=404, detail=MSG_NENHUM_PLANO)

        # Carregar eixos do plano
        eixos_result = await session.execute(
            select(Eixo).where(Eixo.plano_id == plano.id).order_by(Eixo.numero)
        )
        eixos = eixos_result.scalars().all()

        return PlanoDetail(
            id=plano.id,
            nome=plano.nome,
            versao=plano.versao,
            ano_referencia=plano.ano_referencia,
            fonte_url=plano.fonte_url,
            vigencia_inicio=plano.vigencia_inicio,
            vigencia_fim=plano.vigencia_fim,
            eixos=[EixoBase.model_validate(e) for e in eixos],
        )
    except HTTPException:
        raise
    except Exception:
        logger.error("Erro ao listar planos", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=ErrorDetail(
                message=MSG_ERRO_INTERNO,
                code=CODE_INTERNAL_ERROR,
            ).model_dump(),
        )


@router.get("/planos/{plano_id}", response_model=PlanoDetail | ErrorResponse)
@limiter.limit(RATE_LIMIT_PUBLIC_READ)
async def get_plano(
    request: Request,
    plano_id: str,
    session: AsyncSession = Depends(get_db),
) -> PlanoDetail | ErrorResponse:
    """Obter plano por ID.

    Retorna os detalhes de um plano específico, incluindo seus eixos.
    """
    try:
        result = await session.execute(select(Plano).where(Plano.id == plano_id))
        plano = result.scalar_one_or_none()
        if not plano:
            raise HTTPException(
                status_code=404,
                detail=ErrorDetail(
                    message=f"{MSG_PREFIX_PLANO}: {plano_id}",
                    code=CODE_NOT_FOUND,
                ).model_dump(),
            )

        # Carregar eixos do plano
        eixos_result = await session.execute(
            select(Eixo).where(Eixo.plano_id == plano.id).order_by(Eixo.numero)
        )
        eixos = eixos_result.scalars().all()

        return PlanoDetail(
            id=plano.id,
            nome=plano.nome,
            versao=plano.versao,
            ano_referencia=plano.ano_referencia,
            fonte_url=plano.fonte_url,
            vigencia_inicio=plano.vigencia_inicio,
            vigencia_fim=plano.vigencia_fim,
            eixos=[EixoBase.model_validate(e) for e in eixos],
        )
    except HTTPException:
        raise
    except Exception:
        logger.error("Erro ao obter plano {}", plano_id, exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=ErrorDetail(
                message=MSG_ERRO_INTERNO,
                code=CODE_INTERNAL_ERROR,
            ).model_dump(),
        )


# ============================================================================
# Endpoints - Eixo
# ============================================================================


@router.get("/eixos", response_model=EixoListResponse | ErrorResponse)
@limiter.limit(RATE_LIMIT_PUBLIC_READ)
async def list_eixos(
    request: Request,
    page: int = Query(default=DEFAULT_PAGE, ge=1),
    page_size: int = Query(default=DEFAULT_PAGE_SIZE, ge=1, le=MAX_PAGE_SIZE),
    session: AsyncSession = Depends(get_db),
) -> EixoListResponse | ErrorResponse:
    """Listar todos os eixos.

    Retorna uma lista paginada de todos os eixos do PBIA.

    Parâmetros:
    - page: Número da página (padrão: {DEFAULT_PAGE})
    - page_size: Itens por página (padrão: {DEFAULT_PAGE_SIZE}, máximo: {MAX_PAGE_SIZE})
    """
    try:
        # Contar total
        count_result = await session.execute(select(func.count()).select_from(Eixo))
        total = count_result.scalar() or 0

        # Obter página
        offset = (page - 1) * page_size
        result = await session.execute(
            select(Eixo).order_by(Eixo.numero).offset(offset).limit(page_size)
        )
        eixos = result.scalars().all()

        pages = (total + page_size - 1) // page_size if page_size > 0 else 0

        return EixoListResponse(
            data=[EixoBase.model_validate(e) for e in eixos],
            total=total,
            page=page,
            page_size=page_size,
            pages=pages,
        )
    except HTTPException:
        raise
    except Exception:
        logger.error("Erro ao listar eixos", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=ErrorDetail(
                message=MSG_ERRO_INTERNO,
                code=CODE_INTERNAL_ERROR,
            ).model_dump(),
        )


@router.get("/eixos/{eixo_id}", response_model=EixoDetail | ErrorResponse)
@limiter.limit(RATE_LIMIT_PUBLIC_READ)
async def get_eixo(
    request: Request,
    eixo_id: str,
    session: AsyncSession = Depends(get_db),
) -> EixoDetail | ErrorResponse:
    """Obter eixo por ID.

    Retorna os detalhes de um eixo específico, incluindo seus programas.
    """
    try:
        result = await session.execute(select(Eixo).where(Eixo.id == eixo_id))
        eixo = result.scalar_one_or_none()
        if not eixo:
            raise HTTPException(
                status_code=404,
                detail=ErrorDetail(
                    message=f"{MSG_PREFIX_EIXO}: {eixo_id}",
                    code=CODE_NOT_FOUND,
                ).model_dump(),
            )

        # Carregar programas do eixo
        programas_result = await session.execute(
            select(Programa).where(Programa.eixo_id == eixo.id).order_by(Programa.nome)
        )
        programas = programas_result.scalars().all()

        return EixoDetail(
            id=eixo.id,
            numero=eixo.numero,
            nome=eixo.nome,
            descricao=eixo.descricao,
            programas=[ProgramaBase.model_validate(p) for p in programas],
        )
    except HTTPException:
        raise
    except Exception:
        logger.error("Erro ao obter eixo {}", eixo_id, exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=ErrorDetail(
                message=MSG_ERRO_INTERNO,
                code=CODE_INTERNAL_ERROR,
            ).model_dump(),
        )


# ============================================================================
# Endpoints - Programa
# ============================================================================


@router.get("/programas", response_model=ProgramaListResponse | ErrorResponse)
@limiter.limit(RATE_LIMIT_PUBLIC_READ)
async def list_programas(
    request: Request,
    page: int = Query(default=DEFAULT_PAGE, ge=1),
    page_size: int = Query(default=DEFAULT_PAGE_SIZE, ge=1, le=MAX_PAGE_SIZE),
    session: AsyncSession = Depends(get_db),
) -> ProgramaListResponse | ErrorResponse:
    """Listar todos os programas.

    Retorna uma lista paginada de todos os programas do PBIA.

    Parâmetros:
    - page: Número da página (padrão: {DEFAULT_PAGE})
    - page_size: Itens por página (padrão: {DEFAULT_PAGE_SIZE}, máximo: {MAX_PAGE_SIZE})
    """
    try:
        # Contar total
        count_result = await session.execute(select(func.count()).select_from(Programa))
        total = count_result.scalar() or 0

        # Obter página
        offset = (page - 1) * page_size
        result = await session.execute(
            select(Programa).order_by(Programa.nome).offset(offset).limit(page_size)
        )
        programas = result.scalars().all()

        pages = (total + page_size - 1) // page_size if page_size > 0 else 0

        return ProgramaListResponse(
            data=[ProgramaBase.model_validate(p) for p in programas],
            total=total,
            page=page,
            page_size=page_size,
            pages=pages,
        )
    except HTTPException:
        raise
    except Exception:
        logger.error("Erro ao listar programas", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=ErrorDetail(
                message=MSG_ERRO_INTERNO,
                code=CODE_INTERNAL_ERROR,
            ).model_dump(),
        )


@router.get("/programas/{programa_id}", response_model=ProgramaDetail | ErrorResponse)
@limiter.limit(RATE_LIMIT_PUBLIC_READ)
async def get_programa(
    request: Request,
    programa_id: str,
    session: AsyncSession = Depends(get_db),
) -> ProgramaDetail | ErrorResponse:
    """Obter programa por ID.

    Retorna os detalhes de um programa específico, incluindo suas ações.
    """
    try:
        result = await session.execute(select(Programa).where(Programa.id == programa_id))
        programa = result.scalar_one_or_none()
        if not programa:
            raise HTTPException(
                status_code=404,
                detail=ErrorDetail(
                    message=f"{MSG_PREFIX_PROGRAMA}: {programa_id}",
                    code=CODE_NOT_FOUND,
                ).model_dump(),
            )

        # Carregar ações do programa
        acoes_result = await session.execute(select(Acao).where(Acao.programa_id == programa.id))
        acoes = acoes_result.scalars().all()

        return ProgramaDetail(
            id=programa.id,
            eixo_id=programa.eixo_id,
            codigo=None,
            nome=programa.nome,
            descricao=programa.descricao,
            acoes=[AcaoBase.model_validate(a) for a in acoes],
        )
    except HTTPException:
        raise
    except Exception:
        logger.error("Erro ao obter programa {}", programa_id, exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=ErrorDetail(
                message=MSG_ERRO_INTERNO,
                code=CODE_INTERNAL_ERROR,
            ).model_dump(),
        )


# ============================================================================
# Endpoints - Ação
# ============================================================================


class AcaoFilter(BaseModel):
    """Filtros para listagem de ações."""

    eixo_id: str | None = Query(default=None, description="Filtrar por eixo")
    programa_id: str | None = Query(default=None, description="Filtrar por programa")
    status: str | None = Query(default=None, description="Filtrar por status")


@router.get("/acoes", response_model=AcaoListResponse | ErrorResponse)
@limiter.limit(RATE_LIMIT_PUBLIC_READ)
async def list_acoes(
    request: Request,
    response: Response,
    page: int = Query(default=DEFAULT_PAGE, ge=1),
    page_size: int = Query(default=DEFAULT_PAGE_SIZE, ge=1, le=MAX_PAGE_SIZE),
    cursor: str | None = Query(
        default=None,
        description="Cursor opaco para a próxima página (paginacão por cursor)",
    ),
    filters: AcaoFilter = Depends(),
    session: AsyncSession = Depends(get_db),
) -> AcaoListResponse | ErrorResponse | Response:
    """Listar todas as ações.

    Retorna uma lista paginada de todas as ações do PBIA.

    Parâmetros:
    - page: Número da página (padrão: {DEFAULT_PAGE})
    - page_size: Itens por página (padrão: {DEFAULT_PAGE_SIZE}, máximo: {MAX_PAGE_SIZE})
    - cursor: Cursor opaco da página anterior (retorna ``next_cursor``)
    - eixo_id: Filtrar por ID do eixo
    - programa_id: Filtrar por ID do programa
    - status: Filtrar por status da ação

    Responde 304 (com header ``ETag``) quando ``If-None-Match`` casa com a
    representação atual (RFC 9110).
    """
    try:
        # Build query
        query = select(Acao)
        conditions = []

        if filters.eixo_id:
            # Filtrar por eixo via programa
            subquery = select(Programa.id).where(Programa.eixo_id == filters.eixo_id)
            conditions.append(Acao.programa_id.in_(subquery))

        if filters.programa_id:
            conditions.append(Acao.programa_id == filters.programa_id)  # type: ignore[arg-type]

        if filters.status:
            conditions.append(Acao.status == filters.status)  # type: ignore[arg-type]

        if conditions:
            query = query.where(and_(*conditions))

        # Contar total
        count_query = select(func.count(Acao.id)).where(*list(conditions))
        count_result = await session.execute(count_query)
        total = count_result.scalar() or 0

        if cursor is not None:
            # Paginação por cursor (keyset em nome + id, estável sob inserções)
            anchor_nome, anchor_id = _decode_cursor(cursor)
            keyset = or_(
                Acao.nome > anchor_nome,
                and_(Acao.nome == anchor_nome, Acao.id > anchor_id),
            )
            query = query.where(keyset)
            result = await session.execute(query.order_by(Acao.nome, Acao.id).limit(page_size + 1))
            rows = list(result.scalars().all())
            has_more = len(rows) > page_size
            acoes = rows[:page_size]
            next_cursor = (
                _encode_cursor(acoes[-1].nome, acoes[-1].id) if has_more and acoes else None
            )
        else:
            # Paginação clássica por page/page_size (LIMIT/OFFSET)
            offset = (page - 1) * page_size
            result = await session.execute(
                query.order_by(Acao.nome, Acao.id).offset(offset).limit(page_size)
            )
            acoes = list(result.scalars().all())
            # Também expõe next_cursor na paginação por page para permitir
            # migração fluida para cursor (bootstrap sem quebrar o contrato).
            has_more = offset + len(acoes) < total
            next_cursor = (
                _encode_cursor(acoes[-1].nome, acoes[-1].id) if has_more and acoes else None
            )

        pages = (total + page_size - 1) // page_size if page_size > 0 else 0

        payload = AcaoListResponse(
            data=[AcaoBase.model_validate(a) for a in acoes],
            total=total,
            page=page,
            page_size=page_size,
            pages=pages,
            next_cursor=next_cursor,
        )
        not_modified = _maybe_not_modified(request, response, _etag_for_payload(payload))
        if not_modified is not None:
            return not_modified
        return payload
    except HTTPException:
        raise
    except Exception:
        logger.error("Erro ao listar ações", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=ErrorDetail(
                message=MSG_ERRO_INTERNO,
                code=CODE_INTERNAL_ERROR,
            ).model_dump(),
        )


@router.get("/acoes/{acao_id}", response_model=AcaoDetail | ErrorResponse)
@limiter.limit(RATE_LIMIT_PUBLIC_READ)
async def get_acao(
    request: Request,
    acao_id: str,
    session: AsyncSession = Depends(get_db),
) -> AcaoDetail | ErrorResponse:
    """Obter ação por ID.

    Retorna os detalhes de uma ação específica, incluindo:
    - Metas
    - Indicadores
    - Recursos
    - Instituições relacionadas
    """
    try:
        result = await session.execute(select(Acao).where(Acao.id == acao_id))
        acao = result.scalar_one_or_none()
        if not acao:
            raise HTTPException(
                status_code=404,
                detail=ErrorDetail(
                    message=f"{MSG_PREFIX_ACAO}: {acao_id}",
                    code=CODE_NOT_FOUND,
                ).model_dump(),
            )

        # Carregar metas
        metas_result = await session.execute(select(Meta).where(Meta.acao_id == acao.id))
        metas = metas_result.scalars().all()

        # Carregar indicadores (batch query via meta IDs)
        indicadores: list[Indicador] = []
        if metas:
            meta_ids = [m.id for m in metas]
            ind_result = await session.execute(
                select(Indicador).where(Indicador.meta_id.in_(meta_ids))
            )
            indicadores.extend(ind_result.scalars().all())

        # Carregar recursos
        recursos_result = await session.execute(select(Recurso).where(Recurso.acao_id == acao.id))
        recursos = recursos_result.scalars().all()

        # Carregar instituições
        instituicoes_result = await session.execute(
            select(AcaoInstituicao, Instituicao)
            .join(Instituicao, AcaoInstituicao.instituicao_id == Instituicao.id)
            .where(AcaoInstituicao.acao_id == acao.id)
        )
        acao_instituicoes = []
        for row in instituicoes_result:
            ai, inst = row
            acao_instituicoes.append(
                AcaoInstituicaoBase(
                    papel=ai.papel,
                    instituicao=InstituicaoBase.model_validate(inst),
                )
            )

        return AcaoDetail(
            id=acao.id,
            programa_id=acao.programa_id,
            codigo_oficial=acao.codigo_oficial,
            nome=acao.nome,
            descricao=acao.descricao,
            status=acao.status,
            prazo=acao.prazo,
            pagina_doc=acao.pagina_doc,
            metas=[MetaBase.model_validate(m) for m in metas],
            indicadores=[IndicadorBase.model_validate(i) for i in indicadores],
            recursos=[RecursoBase.model_validate(r) for r in recursos],
            instituicoes=acao_instituicoes,
        )
    except HTTPException:
        raise
    except Exception:
        logger.error("Erro ao obter ação {}", acao_id, exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=ErrorDetail(
                message=MSG_ERRO_INTERNO,
                code=CODE_INTERNAL_ERROR,
            ).model_dump(),
        )


# ============================================================================
# Endpoints - Dashboard
# ============================================================================


class DashboardResponse(BaseModel):
    """Resposta para dados do dashboard."""

    indicadores: list[IndicadorBase] = Field(
        default_factory=list, description="Lista de indicadores chave"
    )
    metricas: list[dict[str, Any]] = Field(default_factory=list, description="Métricas calculadas")
    status_summary: list[dict[str, Any]] = Field(
        default_factory=list, description="Resumo de status das ações"
    )


@router.get("/dashboard", response_model=DashboardResponse | ErrorResponse)
@limiter.limit(RATE_LIMIT_PUBLIC_READ)
async def get_dashboard_data(
    request: Request,
    response: Response,
    session: AsyncSession = Depends(get_db),
) -> DashboardResponse | ErrorResponse | Response:
    """Obter dados para o dashboard.

    Retorna indicadores, métricas e resumo de status para exibição no dashboard.
    Responde 304 (com header ``ETag``) quando ``If-None-Match`` casa com a
    representação atual (RFC 9110).
    """
    try:
        # Contar total de ações
        total_result = await session.execute(select(func.count()).select_from(Acao))
        total_acoes = total_result.scalar() or 0

        # Contar ações por status via SQL (GROUP BY)
        status_result = await session.execute(
            select(Acao.status, func.count(Acao.id)).group_by(Acao.status)
        )
        status_counts: dict[str, int] = {}
        for row in status_result:
            status_val = row[0]
            key = status_val.value if hasattr(status_val, "value") else str(status_val)
            status_counts[key] = row[1]

        # Calcular status summary
        status_summary: list[dict[str, Any]] = []
        for status, count in status_counts.items():
            status_summary.append(
                {
                    "status": status,
                    "count": count,
                    "percentage": (
                        round((count / total_acoes) * PERCENTAGE_MULTIPLIER)
                        if total_acoes > 0
                        else 0
                    ),
                }
            )

        # Calcular métricas
        delivered_count = status_counts.get(StatusAcao.entregue.value, 0) + status_counts.get(
            StatusAcao.parcialmente_entregue.value, 0
        )
        initiated_count = status_counts.get(StatusAcao.em_andamento.value, 0) + delivered_count
        progresso_geral = (
            round((delivered_count / total_acoes) * PERCENTAGE_MULTIPLIER) if total_acoes > 0 else 0
        )

        # Calcular investimento total dos recursos
        investimento_result = await session.execute(
            select(func.coalesce(func.sum(Recurso.valor_previsto), 0))
        )
        investimento_raw = investimento_result.scalar_one()
        investimento_total = float(investimento_raw) if investimento_raw is not None else 0.0

        # Calcular prazo médio em anos
        hoje = date.today()
        prazo_result = await session.execute(
            select(func.avg(func.extract("epoch", Acao.prazo))).where(Acao.prazo.isnot(None))
        )
        prazo_medio_raw = prazo_result.scalar_one()
        if prazo_medio_raw is not None:
            # avg(extract(epoch)) retorna segundos (float) em PostgreSQL e SQLite
            prazo_date = (datetime(1970, 1, 1) + timedelta(seconds=float(prazo_medio_raw))).date()
            dias_restantes = (prazo_date - hoje).days
            prazo_medio = round(dias_restantes / DAYS_PER_YEAR, 1)
        else:
            prazo_medio = 0.0

        metricas: list[dict[str, Any]] = [
            {
                "id": METRIC_ID_TOTAL,
                "nome": METRIC_NAME_TOTAL,
                "valor": total_acoes,
                "unidade": UNIDADE_ACOES,
                "descricao": METRIC_DESC_TOTAL,
            },
            {
                "id": METRIC_ID_INICIADAS,
                "nome": METRIC_NAME_INICIADAS,
                "valor": initiated_count,
                "unidade": UNIDADE_ACOES,
                "descricao": METRIC_DESC_INICIADAS,
            },
            {
                "id": METRIC_ID_ENTREGUES,
                "nome": METRIC_NAME_ENTREGUES,
                "valor": delivered_count,
                "unidade": UNIDADE_ACOES,
                "descricao": METRIC_DESC_ENTREGUES,
            },
            {
                "id": METRIC_ID_INVESTIMENTO,
                "nome": METRIC_NAME_INVESTIMENTO,
                "valor": investimento_total,
                "unidade": UNIDADE_MOEDA,
                "descricao": METRIC_DESC_INVESTIMENTO,
            },
            {
                "id": METRIC_ID_PRAZO,
                "nome": METRIC_NAME_PRAZO,
                "valor": prazo_medio,
                "unidade": UNIDADE_TEMPO,
                "descricao": METRIC_DESC_PRAZO,
            },
            {
                "id": METRIC_ID_PROGRESSO,
                "nome": METRIC_NAME_PROGRESSO,
                "valor": progresso_geral,
                "unidade": UNIDADE_PERCENTUAL,
                "descricao": METRIC_DESC_PROGRESSO,
            },
        ]

        # Obter indicadores (paginados para evitar carregar todos)
        indicadores_result = await session.execute(
            select(Indicador).limit(DASHBOARD_INDICADORES_LIMIT)
        )
        indicadores = indicadores_result.scalars().all()

        payload = DashboardResponse(
            indicadores=[IndicadorBase.model_validate(i) for i in indicadores],
            metricas=metricas,
            status_summary=status_summary,
        )
        not_modified = _maybe_not_modified(request, response, _etag_for_payload(payload))
        if not_modified is not None:
            return not_modified
        return payload
    except HTTPException:
        raise
    except Exception:
        logger.error("Erro ao obter dados do dashboard", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=ErrorDetail(
                message=MSG_ERRO_INTERNO,
                code=CODE_INTERNAL_ERROR,
            ).model_dump(),
        )


# ============================================================================
# Schemas - Timeline
# ============================================================================


class PBIALinkEvento(BaseModel):
    """Evento no formato do frontend."""

    id: str
    acao_id: str | None = None
    acao_nome: str
    tipo: str
    descricao: str
    data: str
    fonte_url: str | None = None


class PBIALinkStatusChange(BaseModel):
    """Mudança de status no formato do frontend."""

    id: str
    acao_id: str | None = None
    acao_nome: str
    status_anterior: str | None = None
    status_novo: str
    data: str
    justificativa: str


class PBIALinkTimelineResponse(BaseModel):
    """Resposta de timeline no formato do frontend."""

    eventos: list[PBIALinkEvento]
    statusChanges: list[PBIALinkStatusChange]


# ============================================================================
# Endpoints - Timeline
# ============================================================================


def _resolve_acao_nome(acao: Acao | None, acao_id: str | None) -> str:
    """Resolve o nome de exibição da ação.

    Eventos de nível de plano (acao_id vazio) retornam 'Plano PBIA'
    em vez de uma mensagem de 'não encontrada'.
    """
    if acao is not None:
        return acao.nome
    if acao_id:
        return f"{MSG_ACAO_PREFIX} {acao_id}"
    return "Plano PBIA"


@router.get("/timeline", response_model=PBIALinkTimelineResponse | ErrorResponse)
@limiter.limit(RATE_LIMIT_PUBLIC_READ)
async def get_pbia_timeline(
    request: Request,
    page: int = Query(default=DEFAULT_PAGE, ge=1),
    page_size: int = Query(default=DEFAULT_PAGE_SIZE, ge=1, le=MAX_PAGE_SIZE),
    session: AsyncSession = Depends(get_db),
) -> PBIALinkTimelineResponse | ErrorResponse:
    """Obter timeline do PBIA.

    Retorna eventos e mudanças de status em formato compatível com o frontend.

    Parâmetros:
    - page: Número da página (padrão: {DEFAULT_PAGE})
    - page_size: Itens por página (padrão: {DEFAULT_PAGE_SIZE}, máximo: {MAX_PAGE_SIZE})
    """
    try:
        offset = (page - 1) * page_size

        # Load eventos with action info (SQL pagination)
        eventos_result = await session.execute(
            select(Evento)
            .options(joinedload(Evento.acao))
            .order_by(Evento.data_evento.desc())
            .offset(offset)
            .limit(page_size)
        )
        eventos = eventos_result.unique().scalars().all()

        # Load status changes with action info (SQL pagination)
        changes_result = await session.execute(
            select(AuditLog)
            .options(joinedload(AuditLog.acao))
            .order_by(AuditLog.data_criacao.desc())
            .offset(offset)
            .limit(page_size)
        )
        changes = changes_result.unique().scalars().all()

        eventos_list: list[dict[str, Any]] = []
        for evento in eventos:
            acao_nome = _resolve_acao_nome(evento.acao, evento.acao_id)
            tipo_value = evento.tipo.value if hasattr(evento.tipo, "value") else str(evento.tipo)
            eventos_list.append(
                {
                    "id": evento.id,
                    "acao_id": evento.acao_id,
                    "acao_nome": acao_nome,
                    "tipo": tipo_value.lower(),
                    "descricao": evento.descricao,
                    "data": evento.data_evento.isoformat(),
                    "fonte_url": evento.fonte_url,
                }
            )

        status_changes_list: list[dict[str, Any]] = []
        for change in changes:
            acao_nome = _resolve_acao_nome(change.acao, change.acao_id)
            status_anterior = change.status_anterior.value if change.status_anterior else None
            status_novo = (
                change.status_novo.value
                if hasattr(change.status_novo, "value")
                else str(change.status_novo)
            )
            status_changes_list.append(
                {
                    "id": change.id,
                    "acao_id": change.acao_id,
                    "acao_nome": acao_nome,
                    "status_anterior": status_anterior,
                    "status_novo": status_novo,
                    "data": change.data_criacao.isoformat(),
                    "justificativa": change.justificativa,
                }
            )

        return PBIALinkTimelineResponse(
            eventos=[PBIALinkEvento(**e) for e in eventos_list],
            statusChanges=[PBIALinkStatusChange(**sc) for sc in status_changes_list],
        )
    except HTTPException:
        raise
    except Exception:
        logger.error("Erro ao obter timeline do PBIA", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=ErrorDetail(
                message=MSG_ERRO_INTERNO,
                code=CODE_INTERNAL_ERROR,
            ).model_dump(),
        )


# ---------------------------------------------------------------------------
# Boletim Executivo — Situação do PBIA
# ---------------------------------------------------------------------------


class SituacaoEixo(BaseModel):
    """Dados de situação de um eixo para o boletim executivo."""

    eixo_id: str
    eixo_numero: int
    eixo_nome: str
    total_acoes: int
    entregues: int
    em_andamento: int
    nao_iniciados: int
    outros: int
    atrasadas: int
    percentual_concluido: float


class SituacaoPBIA(BaseModel):
    """Resposta do boletim executivo do PBIA."""

    total_acoes: int
    total_entregues: int
    total_em_andamento: int
    total_nao_iniciados: int
    total_atrasadas: int
    percentual_geral: float
    resumo_texto: str
    eixos: list[SituacaoEixo]


def _situacao_acoes(acoes: list[Acao], hoje: date) -> tuple[int, int, int, int, int]:
    """Agrega status de um conjunto de ações (entregues, em andamento, etc.)."""
    entregues = 0
    em_andamento = 0
    nao_iniciados = 0
    outros = 0
    atrasadas = 0

    for acao in acoes:
        status = acao.status.value if hasattr(acao.status, "value") else str(acao.status)
        if status in ("entregue", "parcialmente_entregue"):
            entregues += 1
        elif status == "em_andamento":
            em_andamento += 1
        elif status == "nao_iniciado":
            nao_iniciados += 1
        else:
            outros += 1

        is_concluido = status in ("entregue", "parcialmente_entregue")
        is_overdue = acao.prazo is not None and acao.prazo < hoje and not is_concluido
        if is_overdue:
            atrasadas += 1

    return entregues, em_andamento, nao_iniciados, outros, atrasadas


@router.get("/situacao", response_model=SituacaoPBIA | ErrorResponse)
@limiter.limit(RATE_LIMIT_PUBLIC_READ)
async def get_situacao_pbia(
    request: Request,
    session: AsyncSession = Depends(get_db),
) -> SituacaoPBIA | ErrorResponse:
    """Boletim executivo: situação geral do PBIA.

    Retorna progresso por eixo, ações atrasadas e resumo textual.
    """
    try:
        hoje = date.today()

        eixos_result = await session.execute(select(Eixo).order_by(Eixo.numero))
        eixos = list(eixos_result.scalars())

        # Carregar programa→eixo e ações em consultas únicas (sem N+1 por eixo)
        prog_result = await session.execute(select(Programa.id, Programa.eixo_id))
        programa_eixo: dict[str, str] = {row[0]: row[1] for row in prog_result}

        acoes_result = await session.execute(select(Acao))
        acoes = list(acoes_result.scalars())

        acoes_por_eixo: dict[str, list[Acao]] = {eixo.id: [] for eixo in eixos}
        for acao in acoes:
            eixo_id = programa_eixo.get(acao.programa_id)
            if eixo_id is not None:
                acoes_por_eixo[eixo_id].append(acao)

        total_geral = 0
        entregues_geral = 0
        em_andamento_geral = 0
        nao_iniciados_geral = 0
        atrasadas_geral = 0
        eixos_data: list[SituacaoEixo] = []

        for eixo in eixos:
            acoes_eixo = acoes_por_eixo[eixo.id]
            total = len(acoes_eixo)
            entregues, em_andamento, nao_iniciados, outros, atrasadas = _situacao_acoes(
                acoes_eixo, hoje
            )
            pct = round((entregues / total) * 100, 1) if total > 0 else 0.0

            eixos_data.append(
                SituacaoEixo(
                    eixo_id=eixo.id,
                    eixo_numero=eixo.numero,
                    eixo_nome=eixo.nome,
                    total_acoes=total,
                    entregues=entregues,
                    em_andamento=em_andamento,
                    nao_iniciados=nao_iniciados,
                    outros=outros,
                    atrasadas=atrasadas,
                    percentual_concluido=pct,
                )
            )

            total_geral += total
            entregues_geral += entregues
            em_andamento_geral += em_andamento
            nao_iniciados_geral += nao_iniciados
            atrasadas_geral += atrasadas

        pct_geral = round((entregues_geral / total_geral) * 100, 1) if total_geral > 0 else 0.0

        if atrasadas_geral > 0:
            resumo = (
                f"O PBIA está {pct_geral}% concluído. "
                f"{atrasadas_geral} ação(ões) está(ão) em atraso."
            )
        else:
            resumo = f"O PBIA está {pct_geral}% concluído. Nenhuma ação em atraso."

        return SituacaoPBIA(
            total_acoes=total_geral,
            total_entregues=entregues_geral,
            total_em_andamento=em_andamento_geral,
            total_nao_iniciados=nao_iniciados_geral,
            total_atrasadas=atrasadas_geral,
            percentual_geral=pct_geral,
            resumo_texto=resumo,
            eixos=eixos_data,
        )
    except Exception:
        logger.error("Erro ao obter situação do PBIA", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=ErrorDetail(
                message=MSG_ERRO_INTERNO,
                code=CODE_INTERNAL_ERROR,
            ).model_dump(),
        )


# ---------------------------------------------------------------------------
# Comparação transparente: oficial (CGEE) x evidências próprias (issue #1103)
# ---------------------------------------------------------------------------


class RelatorioOficialInfo(BaseModel):
    """Dados do relatório oficial de execução do PBIA (CGEE)."""

    titulo: str = Field(..., description="Título do relatório oficial")
    fonte_url: str = Field(..., description="Página do portal CGEE coletada")
    periodicidade: str = Field("2x/ano", description="Cadência declarada de reporte")
    ultima_referencia: date | None = Field(
        None, description="Data do relatório mais recente (quando parseável)"
    )
    data_coleta: date | None = Field(
        None, description="Data em que o IA Brasil coletou a página pela última vez"
    )
    url_pdf: str | None = Field(None, description="URL do PDF do relatório (se encontrada)")
    status_parse: str = Field("abstencao", description="'ok' ou 'abstencao'")
    numeros_chave: list[dict[str, Any]] = Field(
        default_factory=list, description="Números-chave extraídos (provisórios)"
    )
    aviso: str | None = Field(None, description="Aviso de abstenção honesta")


class FontePropriaInfo(BaseModel):
    """Última coleta própria de uma fonte do IA Brasil."""

    source: str = Field(..., description="Chave da fonte no registry")
    periodicidade: str | None = Field(None, description="Cadência declarada ('2x/ano' ou 'manual')")
    ultima_coleta: date | None = Field(None, description="Última coleta terminal")
    total_runs: int = Field(..., description="Total de runs registrados")


class ComparacaoMonitoramentoResponse(BaseModel):
    """Comparação transparente oficial (CGEE) x evidências próprias do IA Brasil."""

    relatorio_oficial: RelatorioOficialInfo | None = Field(
        None, description="Relatório oficial (None enquanto não coletado)"
    )
    fontes_proprias: list[FontePropriaInfo] = Field(
        default_factory=list, description="Fontes próprias com última coleta"
    )
    ultima_coleta_propria: date | None = Field(
        None, description="Última coleta entre as fontes próprias"
    )
    percentual_proprio: float | None = Field(
        None, description="% de ações concluídas segundo as evidências do IA Brasil"
    )
    divergencia_observada: str = Field(
        ..., description="Divergência entre fontes, exibida e não escondida"
    )
    gerado_em: datetime = Field(..., description="Momento da geração")


def _run_percentual_proprio(
    statuses: list[str],
) -> float | None:
    """Percentual de ações concluídas a partir de uma lista de status."""
    total = len(statuses)
    if total == 0:
        return None
    entregues = sum(1 for s in statuses if s in ("entregue", "parcialmente_entregue"))
    return round(entregues / total * 100, 1)


def _build_divergencia(
    oficial: RelatorioOficialInfo | None,
    percentual_proprio: float | None,
) -> str:
    """Descreve a divergência entre o oficial (CGEE) e as evidências próprias.

    A divergência é sempre exibida, nunca escondida — quando os números
    oficiais não são parseáveis, isso é dito explicitamente (abstenção honesta).
    """
    if oficial is None:
        return (
            "Relatório oficial (CGEE) ainda não coletado pelo IA Brasil — "
            "sem base para comparação numérica."
        )
    if oficial.status_parse != "ok" or not oficial.numeros_chave:
        return (
            "Números oficiais (CGEE) não parseáveis da página do portal "
            "(abstenção honesta). A divergência não está escondida — apenas "
            "não é quantificável sem o PDF do relatório."
        )

    percentuais_oficiais = [
        float(n["valor"])
        for n in oficial.numeros_chave
        if n.get("tipo") == "percentual_avancos" and isinstance(n.get("valor"), (int, float))
    ]
    if not percentuais_oficiais:
        return (
            "Números oficiais (CGEE) extraídos não são percentuais de avanço — "
            "comparação percentual indisponível."
        )
    oficial_pct = max(percentuais_oficiais)
    if percentual_proprio is None:
        return (
            f"Oficial (CGEE) reporta {oficial_pct}% de ações com avanço; "
            "o IA Brasil ainda não possui percentual próprio calculado."
        )
    delta = round(percentual_proprio - oficial_pct, 1)
    return (
        f"Oficial (CGEE): {oficial_pct}% de ações com algum avanço. "
        f"IA Brasil (evidências próprias): {percentual_proprio}% de ações "
        f"concluídas. Diferença: {delta:+} pontos percentuais."
    )


@router.get("/monitoramento", response_model=ComparacaoMonitoramentoResponse | ErrorResponse)
@limiter.limit(RATE_LIMIT_PUBLIC_READ)
async def get_monitoramento_comparacao(
    request: Request,
    session: AsyncSession = Depends(get_db),
) -> ComparacaoMonitoramentoResponse | ErrorResponse:
    """Comparação transparente: relatório oficial (CGEE) x evidências próprias.

    Retorna a última data do relatório oficial do PBIA (fonte primária: CGEE),
    a cadência declarada de reporte (2x/ano) e a última coleta própria do IA
    Brasil, com a divergência entre as fontes sempre exibida.
    """
    try:
        runs_result = await session.execute(
            select(IngestionRun).order_by(
                IngestionRun.source,
                IngestionRun.started_at.asc(),
                IngestionRun.id.asc(),
            )
        )
        runs_by_source: dict[str, list[IngestionRun]] = {}
        for run in runs_result.scalars():
            runs_by_source.setdefault(run.source, []).append(run)

        # ── Relatório oficial (CGEE) ────────────────────────────────────────
        oficial: RelatorioOficialInfo | None = None
        cgee_runs = runs_by_source.get("cgee_relatorio", [])
        terminal_cgee = [r for r in cgee_runs if r.status in ("success", "partial", "error")]
        if terminal_cgee:
            last = terminal_cgee[-1]
            metadata = last.metadata_json or {}
            ultima_ref: date | None = None
            raw_ref = metadata.get("ultima_referencia")
            if isinstance(raw_ref, date):
                ultima_ref = raw_ref
            elif isinstance(raw_ref, str) and raw_ref:
                try:
                    ultima_ref = datetime.fromisoformat(raw_ref).date()
                except ValueError:
                    ultima_ref = None
            numeros = metadata.get("numeros_chave")
            oficial = RelatorioOficialInfo(
                titulo=str(metadata.get("titulo_relatorio") or "Relatório de execução do PBIA"),
                fonte_url=str(metadata.get("fonte_url") or "https://www.cgee.org.br"),
                periodicidade=str(metadata.get("periodicidade") or "2x/ano"),
                ultima_referencia=ultima_ref,
                data_coleta=last.started_at.date() if last.started_at else None,
                url_pdf=(str(metadata["url_pdf"]) if metadata.get("url_pdf") else None),
                status_parse=str(metadata.get("status_parse") or "abstencao"),
                numeros_chave=numeros if isinstance(numeros, list) else [],
                aviso=(str(metadata["aviso"]) if metadata.get("aviso") else None),
            )

        # ── Fontes próprias ─────────────────────────────────────────────────
        fontes_proprias: list[FontePropriaInfo] = []
        ultima_coleta_propria: date | None = None
        for source_name, runs in runs_by_source.items():
            if source_name == "cgee_relatorio":
                continue
            terminal = [r for r in runs if r.status in ("success", "partial", "error")]
            last_date = None
            if terminal:
                last_run = terminal[-1]
                last_date = last_run.started_at.date() if last_run.started_at else None
            metadata = (terminal[-1].metadata_json if terminal else None) or {}
            periodicidade = metadata.get("periodicidade")
            fonte = FontePropriaInfo(
                source=source_name,
                periodicidade=periodicidade if isinstance(periodicidade, str) else None,
                ultima_coleta=last_date,
                total_runs=len(runs),
            )
            fontes_proprias.append(fonte)
            if last_date is not None and (
                ultima_coleta_propria is None or last_date > ultima_coleta_propria
            ):
                ultima_coleta_propria = last_date

        # ── Percentual próprio (evidências do IA Brasil) ────────────────────
        acoes_result = await session.execute(select(Acao.status))
        statuses = [
            (row[0].value if hasattr(row[0], "value") else str(row[0])) for row in acoes_result
        ]
        percentual_proprio = _run_percentual_proprio(statuses)

        divergencia = _build_divergencia(oficial, percentual_proprio)

        return ComparacaoMonitoramentoResponse(
            relatorio_oficial=oficial,
            fontes_proprias=fontes_proprias,
            ultima_coleta_propria=ultima_coleta_propria,
            percentual_proprio=percentual_proprio,
            divergencia_observada=divergencia,
            gerado_em=datetime.now(),
        )
    except Exception:
        logger.error("Erro ao obter comparação de monitoramento", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=ErrorDetail(
                message=MSG_ERRO_INTERNO,
                code=CODE_INTERNAL_ERROR,
            ).model_dump(),
        )


# ---------------------------------------------------------------------------
# Execução Financeira
# ---------------------------------------------------------------------------


class AcaoFinanceira(BaseModel):
    """Dados financeiros de uma ação."""

    acao_id: str | None = None
    acao_nome: str
    codigo_oficial: str | None = None
    valor_empenhado: float
    valor_liquidado: float
    valor_pago: float


class ProgramaFinanceiro(BaseModel):
    """Dados financeiros agregados por programa."""

    codigo_programa: str
    programa: str
    valor_empenhado: float
    valor_liquidado: float
    valor_pago: float


class ExecucaoPorAno(BaseModel):
    """Totais de execução financeira por exercício (ano)."""

    ano: int
    total_empenhado: float
    total_liquidado: float
    total_pago: float


class ExecucaoFinanceiraResponse(BaseModel):
    """Resposta da execução financeira do PBIA."""

    total_empenhado: float
    total_liquidado: float
    total_pago: float
    por_acao: list[AcaoFinanceira]
    por_programa: list[ProgramaFinanceiro]
    por_ano: list[ExecucaoPorAno]


@router.get(
    "/execucao-financeira",
    response_model=ExecucaoFinanceiraResponse | ErrorResponse,
)
@limiter.limit(RATE_LIMIT_PUBLIC_READ)
async def get_execucao_financeira(
    request: Request,
    ano: int | None = Query(default=None, description="Filtrar por exercício (ano)"),
    session: AsyncSession = Depends(get_db),
) -> ExecucaoFinanceiraResponse | ErrorResponse:
    """Retorna execução financeira do PBIA (dados CGU/SIAFI).

    Mostra valores empenhados, liquidados e pagos por ação e por programa,
    com quebra por exercício (``por_ano``). Use ``?ano=2025`` para filtrar
    por um exercício específico.
    """
    try:
        stmt = select(ExecucaoFinanceira)
        if ano is not None:
            stmt = stmt.where(ExecucaoFinanceira.ano == ano)
        result = await session.execute(stmt)
        registros = list(result.scalars())

        if not registros:
            return ExecucaoFinanceiraResponse(
                total_empenhado=0.0,
                total_liquidado=0.0,
                total_pago=0.0,
                por_acao=[],
                por_programa=[],
                por_ano=[],
            )

        total_emp = 0.0
        total_liq = 0.0
        total_pag = 0.0

        acoes_map: dict[str, dict[str, Any]] = {}
        progs_map: dict[str, dict[str, Any]] = {}
        anos_map: dict[int, dict[str, float]] = {}

        for reg in registros:
            emp = float(reg.valor_empenhado or 0)
            liq = float(reg.valor_liquidado or 0)
            pag = float(reg.valor_pago or 0)
            total_emp += emp
            total_liq += liq
            total_pag += pag

            if reg.acao_id:
                key = reg.acao_id
                if key not in acoes_map:
                    acoes_map[key] = {
                        "acao_id": reg.acao_id,
                        "acao_nome": reg.nome_acao,
                        "codigo_oficial": reg.codigo_acao_siafi,
                        "valor_empenhado": 0.0,
                        "valor_liquidado": 0.0,
                        "valor_pago": 0.0,
                    }
                acoes_map[key]["valor_empenhado"] += emp
                acoes_map[key]["valor_liquidado"] += liq
                acoes_map[key]["valor_pago"] += pag

            pkey = reg.codigo_programa
            if pkey not in progs_map:
                progs_map[pkey] = {
                    "codigo_programa": pkey,
                    "programa": reg.programa,
                    "valor_empenhado": 0.0,
                    "valor_liquidado": 0.0,
                    "valor_pago": 0.0,
                }
            progs_map[pkey]["valor_empenhado"] += emp
            progs_map[pkey]["valor_liquidado"] += liq
            progs_map[pkey]["valor_pago"] += pag

            # Quebra por exercício (ano)
            if reg.ano not in anos_map:
                anos_map[reg.ano] = {
                    "total_empenhado": 0.0,
                    "total_liquidado": 0.0,
                    "total_pago": 0.0,
                }
            anos_map[reg.ano]["total_empenhado"] += emp
            anos_map[reg.ano]["total_liquidado"] += liq
            anos_map[reg.ano]["total_pago"] += pag

        por_acao = sorted(
            [AcaoFinanceira(**v) for v in acoes_map.values()],
            key=lambda x: x.valor_pago,
            reverse=True,
        )
        por_programa = sorted(
            [ProgramaFinanceiro(**v) for v in progs_map.values()],
            key=lambda x: x.valor_pago,
            reverse=True,
        )
        por_ano = sorted(
            [ExecucaoPorAno(ano=reg_ano, **valores) for reg_ano, valores in anos_map.items()],
            key=lambda x: x.ano,
        )

        return ExecucaoFinanceiraResponse(
            total_empenhado=round(total_emp, 2),
            total_liquidado=round(total_liq, 2),
            total_pago=round(total_pag, 2),
            por_acao=por_acao,
            por_programa=por_programa,
            por_ano=por_ano,
        )
    except Exception:
        logger.error("Erro ao obter execução financeira", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=ErrorDetail(
                message=MSG_ERRO_INTERNO,
                code=CODE_INTERNAL_ERROR,
            ).model_dump(),
        )


# ---------------------------------------------------------------------------
# Resultados do PBIA (indicadores físicos)
# ---------------------------------------------------------------------------


class IndicadorResultadoItem(BaseModel):
    """Um indicador com meta e valor atingido."""

    indicador_id: str
    indicador_nome: str
    unidade: str | None = None
    meta_valor: float | None = None
    valor_atingido: float | None = None
    percentual: float | None = None
    data_apuracao: str | None = None
    fonte_url: str | None = None


class EixoResultados(BaseModel):
    """Resultados de um eixo do PBIA."""

    eixo_id: str
    eixo_numero: int
    eixo_nome: str
    indicadores: list[IndicadorResultadoItem]


class ResultadosPBIA(BaseModel):
    """Resposta de resultados físicos do PBIA."""

    total_indicadores: int
    indicadores_com_resultado: int
    por_eixo: list[EixoResultados]


@router.get(
    "/resultados",
    response_model=ResultadosPBIA | ErrorResponse,
)
@limiter.limit(RATE_LIMIT_PUBLIC_READ)
async def get_resultados_pbia(
    request: Request,
    session: AsyncSession = Depends(get_db),
) -> ResultadosPBIA | ErrorResponse:
    """Resultados físicos do PBIA — prometido vs. atingido.

    Retorna indicadores com meta e valor atingido, agrupados por eixo.
    """
    try:
        eixos_result = await session.execute(select(Eixo).order_by(Eixo.numero))
        eixos = list(eixos_result.scalars())

        # Mapeamentos carregados em consultas únicas (sem N+1 por eixo/meta/indicador)
        prog_result = await session.execute(select(Programa.id, Programa.eixo_id))
        programa_eixo: dict[str, str] = {row[0]: row[1] for row in prog_result}

        acao_result = await session.execute(select(Acao.id, Acao.programa_id))
        acao_programa: dict[str, str] = {row[0]: row[1] for row in acao_result}

        meta_result = await session.execute(select(Meta.id, Meta.acao_id))
        meta_acao: dict[str, str] = {row[0]: row[1] for row in meta_result}

        inds_result = await session.execute(select(Indicador))
        indicadores = list(inds_result.scalars())

        res_result = await session.execute(select(IndicadorResultado))
        resultados = list(res_result.scalars())

        # Último resultado por indicador (data de apuração mais recente)
        ultimo_resultado: dict[str, IndicadorResultado] = {}
        for resultado_row in resultados:
            atual = ultimo_resultado.get(resultado_row.indicador_id)
            if atual is None or resultado_row.data_apuracao > atual.data_apuracao:
                ultimo_resultado[resultado_row.indicador_id] = resultado_row

        # Agrupar indicadores por eixo via metas → ações → programas
        indicadores_por_eixo: dict[str, list[Indicador]] = {}
        for ind in indicadores:
            acao_id = meta_acao.get(ind.meta_id)
            if acao_id is None:
                continue
            programa_id = acao_programa.get(acao_id)
            if programa_id is None:
                continue
            eixo_id = programa_eixo.get(programa_id)
            if eixo_id is None:
                continue
            indicadores_por_eixo.setdefault(eixo_id, []).append(ind)

        total_ind = 0
        com_resultado = 0
        por_eixo: list[EixoResultados] = []

        for eixo in eixos:
            ind_items: list[IndicadorResultadoItem] = []
            for ind in indicadores_por_eixo.get(eixo.id, []):
                total_ind += 1
                res = ultimo_resultado.get(ind.id)
                resultado = None
                data_ap = None
                fonte = None

                if res is not None:
                    resultado = float(res.valor_atingido)
                    data_ap = str(res.data_apuracao)
                    fonte = res.fonte_url
                    com_resultado += 1

                meta_val = float(ind.meta_valor) if ind.meta_valor else None
                pct = None
                if meta_val and resultado is not None and meta_val > 0:
                    pct = round((resultado / meta_val) * 100, 1)

                ind_items.append(
                    IndicadorResultadoItem(
                        indicador_id=ind.id,
                        indicador_nome=ind.nome,
                        unidade=ind.unidade,
                        meta_valor=meta_val,
                        valor_atingido=resultado,
                        percentual=pct,
                        data_apuracao=data_ap,
                        fonte_url=fonte,
                    )
                )

            por_eixo.append(
                EixoResultados(
                    eixo_id=eixo.id,
                    eixo_numero=eixo.numero,
                    eixo_nome=eixo.nome,
                    indicadores=ind_items,
                )
            )

        return ResultadosPBIA(
            total_indicadores=total_ind,
            indicadores_com_resultado=com_resultado,
            por_eixo=por_eixo,
        )
    except Exception:
        logger.error("Erro ao obter resultados do PBIA", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=ErrorDetail(
                message=MSG_ERRO_INTERNO,
                code=CODE_INTERNAL_ERROR,
            ).model_dump(),
        )
