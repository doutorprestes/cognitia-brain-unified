"""Router para scoring — IA Brasil.

Endpoints para:
- Cálculo de status para ações
- Cálculo em lote
- Atualização de status
- Consulta de status com evidências (GET /acoes/{id}/status)
- Dashboard por eixo (GET /eixos/{id}/dashboard)
- Pipeline de scoring (POST /pipeline/run)

Todos os endpoints de escrita requerem autenticação via API Key.
Endpoints de leitura de status/dashboard são públicos.
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi import status as http_status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from src.core.db import StatusAcao, get_session
from src.core.limiter import (
    RATE_LIMIT_AUTHENTICATED,
    RATE_LIMIT_SENSITIVE,
    RATE_LIMIT_WRITE,
    limiter,
)
from src.modules.auth.dependencies import get_contributor_api_key
from src.modules.scoring.pipeline import ScoringPipeline
from src.modules.scoring.report import ScoringReport
from src.modules.scoring.schemas import (
    BulkScoringRequest,
    BulkScoringResult,
    ScoringRequest,
    ScoringResult,
    StatusCalculation,
)
from src.modules.scoring.service import ScoringService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/scoring", tags=["scoring"])


@router.post(
    "/calculate",
    response_model=ScoringResult,
)
@limiter.limit(RATE_LIMIT_WRITE)
async def calculate_scoring(
    request: Request,
    scoring_request: ScoringRequest,
    _role: str = Depends(get_contributor_api_key),
) -> ScoringResult:
    """Calcula o status para uma ação específica."""
    return await ScoringService.calculate_scoring(scoring_request)


@router.post(
    "/calculate-bulk",
    response_model=BulkScoringResult,
)
@limiter.limit(RATE_LIMIT_WRITE)
async def calculate_bulk_scoring(
    request: Request,
    bulk_request: BulkScoringRequest,
    _role: str = Depends(get_contributor_api_key),
) -> BulkScoringResult:
    """Calcula scoring em lote para múltiplas ações."""
    return await ScoringService.calculate_bulk_scoring(bulk_request)


@router.post(
    "/actions/{acao_id}/status",
    response_model=StatusCalculation,
    status_code=http_status.HTTP_201_CREATED,
)
@limiter.limit(RATE_LIMIT_WRITE)
async def update_action_status(
    request: Request,
    acao_id: str,
    new_status: str,
    justificativa: str,
    _role: str = Depends(get_contributor_api_key),
) -> StatusCalculation:
    """Atualiza manualmente o status de uma ação."""
    valid_statuses = [
        "nao_iniciado",
        "sinalizado",
        "em_andamento",
        "parcialmente_entregue",
        "entregue",
        "inconclusivo",
        "contraditorio",
        "descontinuado",
    ]

    if new_status not in valid_statuses:
        raise HTTPException(
            status_code=http_status.HTTP_400_BAD_REQUEST,
            detail=f"Status inválido. Valores válidos: {', '.join(valid_statuses)}",
        )

    if len(justificativa) < 20:
        raise HTTPException(
            status_code=http_status.HTTP_400_BAD_REQUEST,
            detail="Justificativa deve ter pelo menos 20 caracteres",
        )

    try:
        status_enum = StatusAcao(new_status)
    except ValueError:
        raise HTTPException(
            status_code=http_status.HTTP_400_BAD_REQUEST,
            detail=f"Status inválido: {new_status}",
        )

    try:
        await ScoringService.update_acao_status(
            acao_id=acao_id,
            status=status_enum,
            justificativa=justificativa,
        )
    except ValueError as e:
        raise HTTPException(
            status_code=http_status.HTTP_409_CONFLICT,
            detail=str(e),
        )
    except IntegrityError:
        raise HTTPException(
            status_code=http_status.HTTP_409_CONFLICT,
            detail="Conflito: registro duplicado ou violação de restrição",
        )

    return await ScoringService.calculate_status_for_acao(acao_id)


@router.get(
    "/actions/{acao_id}/calculate",
    response_model=StatusCalculation,
)
@limiter.limit(RATE_LIMIT_AUTHENTICATED)
async def get_action_calculation(
    request: Request,
    acao_id: str,
    _role: str = Depends(get_contributor_api_key),
) -> StatusCalculation:
    """Obtém o cálculo de status para uma ação sem criar avaliação."""
    return await ScoringService.calculate_status_for_acao(acao_id)


@router.get("/stats")
@limiter.limit(RATE_LIMIT_AUTHENTICATED)
async def get_scoring_stats(
    request: Request,
    _role: str = Depends(get_contributor_api_key),
) -> dict[str, Any]:
    """Retorna estatísticas de scoring."""
    from src.core.db import Acao

    async with get_session() as session:
        result = await session.execute(select(Acao))
        acoes = result.scalars().all()

        stats: dict[str, Any] = {
            "total_acoes": len(acoes),
            "acoes_por_status": {},
        }

        for acao in acoes:
            status_val = acao.status.value if hasattr(acao.status, "value") else str(acao.status)
            counts = stats["acoes_por_status"]
            counts[status_val] = counts.get(status_val, 0) + 1

        return stats


# ---------------------------------------------------------------------------
# Endpoints — Status com evidências (público)
# ---------------------------------------------------------------------------


@router.get(
    "/acoes/{acao_id}/status",
    response_model=dict[str, Any],
)
@limiter.limit(RATE_LIMIT_AUTHENTICATED)
async def get_acao_status(request: Request, acao_id: str) -> dict[str, Any]:
    """Retorna status calculado + justificativa + evidências de uma ação.

    Endpoint público para consulta do status de uma ação específica.
    Retorna o status atual, justificativa detalhada, evidências vinculadas
    e informações da última avaliação.
    """
    try:
        return await ScoringReport.get_acao_status(acao_id)
    except ValueError as e:
        raise HTTPException(
            status_code=http_status.HTTP_404_NOT_FOUND,
            detail=str(e),
        )
    except Exception:
        logger.error("Erro ao obter status da ação %s", acao_id, exc_info=True)
        raise HTTPException(
            status_code=http_status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Erro interno do servidor",
        )


# ---------------------------------------------------------------------------
# Endpoints — Dashboard por eixo (público)
# ---------------------------------------------------------------------------


@router.get(
    "/eixos/{eixo_id}/dashboard",
    response_model=dict[str, Any],
)
@limiter.limit(RATE_LIMIT_AUTHENTICATED)
async def get_eixo_dashboard(request: Request, eixo_id: str) -> dict[str, Any]:
    """Retorna dashboard de status agregado por eixo.

    Retorna contagens por status, percentuais e progresso.
    """
    try:
        dashboard = await ScoringReport.get_eixo_dashboard(eixo_id)
        return {
            "eixo_id": dashboard.eixo_id,
            "eixo_nome": dashboard.eixo_nome,
            "total_acoes": dashboard.total_acoes,
            "status_counts": [
                {
                    "status": sc.status.value,
                    "count": sc.count,
                    "percentage": sc.percentage,
                }
                for sc in dashboard.status_counts
            ],
            "progresso_entregue": dashboard.progresso_entregue,
            "progresso_andamento": dashboard.progresso_andamento,
        }
    except ValueError as e:
        raise HTTPException(
            status_code=http_status.HTTP_404_NOT_FOUND,
            detail=str(e),
        )
    except Exception:
        logger.error("Erro ao obter dashboard do eixo %s", eixo_id, exc_info=True)
        raise HTTPException(
            status_code=http_status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Erro interno do servidor",
        )


# ---------------------------------------------------------------------------
# Endpoints — Pipeline (autenticado)
# ---------------------------------------------------------------------------


@router.post(
    "/pipeline/run",
    response_model=dict[str, Any],
)
@limiter.limit(RATE_LIMIT_SENSITIVE)
async def run_scoring_pipeline(
    request: Request,
    _role: str = Depends(get_contributor_api_key),
) -> dict[str, Any]:
    """Executa o pipeline de scoring para todas as ações.

    Pipeline idempotente: re-run não duplica avaliações.
    """
    try:
        result = await ScoringPipeline.run_all()
        return {
            "total": result.total,
            "processadas": result.processadas,
            "atualizadas": result.atualizadas,
            "erros": result.erros,
            "erros_detalhes": result.erros_detalhes,
        }
    except IntegrityError:
        raise HTTPException(
            status_code=http_status.HTTP_409_CONFLICT,
            detail="Conflito: registro duplicado ou violação de restrição",
        )
    except Exception:
        logger.error("Erro ao executar pipeline de scoring", exc_info=True)
        raise HTTPException(
            status_code=http_status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Erro interno do servidor",
        )


@router.post(
    "/pipeline/run/{acao_id}",
    response_model=dict[str, Any],
)
@limiter.limit(RATE_LIMIT_SENSITIVE)
async def run_scoring_for_acao(
    request: Request,
    acao_id: str,
    _role: str = Depends(get_contributor_api_key),
) -> dict[str, Any]:
    """Executa o pipeline de scoring para uma ação específica."""
    try:
        result = await ScoringPipeline.run_for_acao(acao_id)
        return {
            "acao_id": result.acao_id,
            "status_anterior": result.status_anterior.value,
            "status_novo": result.status_novo.value,
            "confidence": result.confidence,
            "justification": result.justification,
            "rules_applied": result.rules_applied,
            "evidence_count": result.evidence_count,
        }
    except ValueError as e:
        raise HTTPException(
            status_code=http_status.HTTP_404_NOT_FOUND,
            detail=str(e),
        )
    except IntegrityError:
        raise HTTPException(
            status_code=http_status.HTTP_409_CONFLICT,
            detail="Conflito: registro duplicado ou violação de restrição",
        )
    except Exception:
        logger.error("Erro ao executar scoring para ação %s", acao_id, exc_info=True)
        raise HTTPException(
            status_code=http_status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Erro interno do servidor",
        )
