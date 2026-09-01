"""Router admin — IA Brasil.

Endpoints administrativos para:
- Gerenciar evidências (CRUD)
- Revisar e gerenciar vínculos
- Gerenciar avaliações
- Dashboard com métricas

Todos os endpoints requerem autenticação via API Key de admin.
"""

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy.exc import IntegrityError

from src.core.limiter import RATE_LIMIT_ADMIN, limiter
from src.modules.admin.schemas import (
    AdminAvaliacaoCreate,
    AdminAvaliacaoFilter,
    AdminAvaliacaoRead,
    AdminAvaliacaoUpdate,
    AdminDashboard,
    AdminEventoFilter,
    AdminEvidenciaCreate,
    AdminEvidenciaFilter,
    AdminEvidenciaRead,
    AdminEvidenciaUpdate,
    AdminPaginatedResponse,
    AdminVinculoApprove,
    AdminVinculoCreate,
    AdminVinculoFilter,
    AdminVinculoRead,
)
from src.modules.admin.service import AdminService
from src.modules.auth.dependencies import get_admin_api_key, get_admin_operator

router = APIRouter(prefix="/admin", tags=["admin"])


# ---------------------------------------------------------------------------
# Dashboard
# ---------------------------------------------------------------------------


@router.get("/dashboard", response_model=AdminDashboard)
@limiter.limit(RATE_LIMIT_ADMIN)
async def get_dashboard(
    request: Request,
    _role: str = Depends(get_admin_api_key),
) -> AdminDashboard:
    """Retorna dados do dashboard admin.

    Inclui métricas de cobertura, últimas coletas e alertas de qualidade.
    Requer role: admin.
    """
    return await AdminService.get_dashboard()


# ---------------------------------------------------------------------------
# Evidências
# ---------------------------------------------------------------------------


@router.get("/evidencias", response_model=AdminPaginatedResponse)
@limiter.limit(RATE_LIMIT_ADMIN)
async def list_evidencias(
    request: Request,
    filters: AdminEvidenciaFilter = Query(),
    _role: str = Depends(get_admin_api_key),
) -> AdminPaginatedResponse:
    """Lista evidências com filtros e paginação.

    Filtros disponíveis: fonte_id, tipo, data_inicio, data_fim,
    confianca_min, confianca_max.
    Requer role: admin.
    """
    return await AdminService.list_evidencias(filters)


@router.get(
    "/evidencias/{evidencia_id}",
    response_model=AdminEvidenciaRead,
)
@limiter.limit(RATE_LIMIT_ADMIN)
async def get_evidencia(
    request: Request,
    evidencia_id: str,
    _role: str = Depends(get_admin_api_key),
) -> AdminEvidenciaRead:
    """Busca uma evidência por ID.

    Retorna evidência com dados da fonte.
    Requer role: admin.
    """
    evidencia = await AdminService.get_evidencia(evidencia_id)
    if not evidencia:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Evidência não encontrada: {evidencia_id}",
        )
    return evidencia


@router.post(
    "/evidencias",
    response_model=AdminEvidenciaRead,
    status_code=status.HTTP_201_CREATED,
)
@limiter.limit(RATE_LIMIT_ADMIN)
async def create_evidencia(
    request: Request,
    data: AdminEvidenciaCreate,
    _role: str = Depends(get_admin_api_key),
) -> AdminEvidenciaRead:
    """Cria uma nova evidência manualmente.

    Requer role: admin.
    """
    try:
        return await AdminService.create_evidencia(data)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(e),
        )
    except IntegrityError as e:
        if "unique" in str(e.orig).lower():
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Conflito: registro duplicado ou violação de restrição",
            ) from e
        raise


@router.put(
    "/evidencias/{evidencia_id}",
    response_model=AdminEvidenciaRead,
)
@limiter.limit(RATE_LIMIT_ADMIN)
async def update_evidencia(
    request: Request,
    evidencia_id: str,
    data: AdminEvidenciaUpdate,
    _role: str = Depends(get_admin_api_key),
) -> AdminEvidenciaRead:
    """Atualiza metadados de uma evidência.

    Apenas campos informados serão atualizados.
    Requer role: admin.
    """
    evidencia = await AdminService.update_evidencia(evidencia_id, data)
    if not evidencia:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Evidência não encontrada: {evidencia_id}",
        )
    return evidencia


@router.delete(
    "/evidencias/{evidencia_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
@limiter.limit(RATE_LIMIT_ADMIN)
async def delete_evidencia(
    request: Request,
    evidencia_id: str,
    _role: str = Depends(get_admin_api_key),
) -> None:
    """Remove uma evidência.

    Requer role: admin.
    """
    deleted = await AdminService.delete_evidencia(evidencia_id)
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Evidência não encontrada: {evidencia_id}",
        )


# ---------------------------------------------------------------------------
# Vínculos
# ---------------------------------------------------------------------------


@router.get("/vinculos", response_model=AdminPaginatedResponse)
@limiter.limit(RATE_LIMIT_ADMIN)
async def list_vinculos(
    request: Request,
    filters: AdminVinculoFilter = Query(),
    _role: str = Depends(get_admin_api_key),
) -> AdminPaginatedResponse:
    """Lista vínculos com filtros e paginação.

    Filtros disponíveis: acao_id, evidencia_id, criado_por.
    Requer role: admin.
    """
    return await AdminService.list_vinculos(filters)


@router.get(
    "/vinculos/{vinculo_id}",
    response_model=AdminVinculoRead,
)
@limiter.limit(RATE_LIMIT_ADMIN)
async def get_vinculo(
    request: Request,
    vinculo_id: str,
    _role: str = Depends(get_admin_api_key),
) -> AdminVinculoRead:
    """Busca um vínculo por ID.

    Retorna vínculo com dados da evidência e ação.
    Requer role: admin.
    """
    vinculo = await AdminService.get_vinculo(vinculo_id)
    if not vinculo:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Vínculo não encontrado: {vinculo_id}",
        )
    return vinculo


@router.post(
    "/vinculos",
    response_model=AdminVinculoRead,
    status_code=status.HTTP_201_CREATED,
)
@limiter.limit(RATE_LIMIT_ADMIN)
async def create_vinculo(
    request: Request,
    data: AdminVinculoCreate,
    _role: str = Depends(get_admin_api_key),
    operador: str = Depends(get_admin_operator),
) -> AdminVinculoRead:
    """Cria um novo vínculo manualmente.

    Vincula uma evidência a uma ação/meta. O operador autenticado é
    registrado como revisor quando a criação aprova o vínculo.
    Requer role: admin.
    """
    try:
        return await AdminService.create_vinculo(data, operador=operador)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(e),
        )
    except IntegrityError as e:
        if "unique" in str(e.orig).lower():
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Conflito: registro duplicado ou violação de restrição",
            ) from e
        raise


@router.post(
    "/vinculos/{vinculo_id}/avaliar",
    response_model=AdminVinculoRead | None,
)
@limiter.limit(RATE_LIMIT_ADMIN)
async def approve_vinculo(
    request: Request,
    vinculo_id: str,
    data: AdminVinculoApprove,
    _role: str = Depends(get_admin_api_key),
    operador: str = Depends(get_admin_operator),
) -> AdminVinculoRead | None:
    """Aprova ou rejeita um vínculo.

    A decisão é registrada com o operador autenticado (revisor) e timestamp.
    Rejeição mantém o vínculo com estado ``rejeitado`` na fila de revisão.
    Requer role: admin.
    """
    result = await AdminService.approve_vinculo(vinculo_id, data, operador=operador)
    if result is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Vínculo não encontrado: {vinculo_id}",
        )
    return result


@router.delete(
    "/vinculos/{vinculo_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
@limiter.limit(RATE_LIMIT_ADMIN)
async def delete_vinculo(
    request: Request,
    vinculo_id: str,
    _role: str = Depends(get_admin_api_key),
) -> None:
    """Remove um vínculo.

    Requer role: admin.
    """
    deleted = await AdminService.delete_vinculo(vinculo_id)
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Vínculo não encontrado: {vinculo_id}",
        )


# ---------------------------------------------------------------------------
# Avaliações
# ---------------------------------------------------------------------------


@router.get("/avaliacoes", response_model=AdminPaginatedResponse)
@limiter.limit(RATE_LIMIT_ADMIN)
async def list_avaliacoes(
    request: Request,
    filters: AdminAvaliacaoFilter = Query(),
    _role: str = Depends(get_admin_api_key),
) -> AdminPaginatedResponse:
    """Lista avaliações com filtros e paginação.

    Filtros disponíveis: acao_id, status, avaliado_por.
    Requer role: admin.
    """
    return await AdminService.list_avaliacoes(filters)


@router.get(
    "/avaliacoes/{avaliacao_id}",
    response_model=AdminAvaliacaoRead,
)
@limiter.limit(RATE_LIMIT_ADMIN)
async def get_avaliacao(
    request: Request,
    avaliacao_id: str,
    _role: str = Depends(get_admin_api_key),
) -> AdminAvaliacaoRead:
    """Busca uma avaliação por ID.

    Requer role: admin.
    """
    avaliacao = await AdminService.get_avaliacao(avaliacao_id)
    if not avaliacao:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Avaliação não encontrada: {avaliacao_id}",
        )
    return avaliacao


@router.post(
    "/avaliacoes",
    response_model=AdminAvaliacaoRead,
    status_code=status.HTTP_201_CREATED,
)
@limiter.limit(RATE_LIMIT_ADMIN)
async def create_avaliacao(
    request: Request,
    data: AdminAvaliacaoCreate,
    _role: str = Depends(get_admin_api_key),
) -> AdminAvaliacaoRead:
    """Cria uma nova avaliação.

    Requer role: admin.
    """
    try:
        return await AdminService.create_avaliacao(data)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(e),
        )
    except IntegrityError as e:
        if "unique" in str(e.orig).lower():
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Conflito: registro duplicado ou violação de restrição",
            ) from e
        raise


@router.put(
    "/avaliacoes/{avaliacao_id}",
    response_model=AdminAvaliacaoRead,
)
@limiter.limit(RATE_LIMIT_ADMIN)
async def update_avaliacao(
    request: Request,
    avaliacao_id: str,
    data: AdminAvaliacaoUpdate,
    _role: str = Depends(get_admin_api_key),
) -> AdminAvaliacaoRead:
    """Atualiza uma avaliação existente.

    Incrementa automaticamente a versão.
    Requer role: admin.
    """
    avaliacao = await AdminService.update_avaliacao(avaliacao_id, data)
    if not avaliacao:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Avaliação não encontrada: {avaliacao_id}",
        )
    return avaliacao


@router.get(
    "/avaliacoes/acao/{acao_id}/historico",
    response_model=list[AdminAvaliacaoRead],
)
@limiter.limit(RATE_LIMIT_ADMIN)
async def get_avaliacao_history(
    request: Request,
    acao_id: str,
    _role: str = Depends(get_admin_api_key),
) -> list[AdminAvaliacaoRead]:
    """Retorna histórico de avaliações de uma ação.

    Lista todas as avaliações ordenadas por data e versão.
    Requer role: admin.
    """
    return await AdminService.get_avaliacao_history(acao_id)


# ---------------------------------------------------------------------------
# Eventos
# ---------------------------------------------------------------------------


@router.get("/eventos", response_model=AdminPaginatedResponse)
@limiter.limit(RATE_LIMIT_ADMIN)
async def list_eventos(
    request: Request,
    filters: AdminEventoFilter = Query(),
    _role: str = Depends(get_admin_api_key),
) -> AdminPaginatedResponse:
    """Lista eventos com filtros e paginação.

    Filtros disponíveis: acao_id, tipo (str), limit, offset.
    Requer role: admin.
    """
    return await AdminService.list_eventos(filters)
