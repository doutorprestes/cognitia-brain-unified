"""Router para coleta de dados — IA Brasil.

Endpoints para execução e monitoramento de coleta automática.
"""

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from loguru import logger
from sqlalchemy.exc import IntegrityError

from src.core.limiter import RATE_LIMIT_WRITE, limiter
from src.modules.auth.dependencies import get_contributor_api_key
from src.modules.collector.schemas import CollectorResult, CollectorType
from src.modules.collector.service import CollectorService, create_collector_service

# Configuração do router
router = APIRouter(
    prefix="/collector",
    tags=["collector"],
    dependencies=[Depends(get_contributor_api_key)],
)

# Serviço de coleta (inicializado no startup)
collector_service: CollectorService = create_collector_service()


@router.get("/sources", response_model=dict[str, str])
@limiter.limit(RATE_LIMIT_WRITE)
async def list_sources(request: Request) -> dict[str, str]:
    """Lista todos os coletores disponíveis."""
    sources = {}
    for name, collector in collector_service.collectors.items():
        sources[name.value] = str(collector.source_url)
    return sources


@router.post("/collect/{source_name}", response_model=CollectorResult)
@limiter.limit(RATE_LIMIT_WRITE)
async def collect_source(
    request: Request,
    source_name: CollectorType,
    parallel: bool = False,
) -> CollectorResult:
    """Executa coleta para uma fonte específica."""
    try:
        return await collector_service.collect(source_name, parallel=parallel)
    except HTTPException:
        raise
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except IntegrityError:
        raise HTTPException(
            status_code=409,
            detail="Conflito: registro duplicado ou violação de restrição",
        )
    except Exception:
        logger.error("Erro na coleta para {}", source_name, exc_info=True)
        raise HTTPException(status_code=500, detail="Erro interno do servidor")


@router.post("/collect-all", response_model=dict[str, CollectorResult])
@limiter.limit(RATE_LIMIT_WRITE)
async def collect_all_sources(
    request: Request,
    parallel: bool = True,
) -> dict[str, CollectorResult]:
    """Executa coleta para todas as fontes."""
    try:
        return await collector_service.collect_all(parallel=parallel)
    except HTTPException:
        raise
    except Exception:
        logger.error("Erro na coleta de todas as fontes", exc_info=True)
        raise HTTPException(status_code=500, detail="Erro interno do servidor")


@router.get("/status")
@limiter.limit(RATE_LIMIT_WRITE)
async def collector_status(request: Request) -> dict[str, dict[str, Any]]:
    """Retorna status dos coletores.

    Returns status degradado para coletores ainda não implementados,
    evitando reportar estado falso de funcionalidade completa.
    """
    status = {}
    for name, collector in collector_service.collectors.items():
        is_stub = hasattr(collector, "_is_stub") and collector._is_stub
        status[name.value] = {
            "source_url": str(collector.source_url),
            "schedule": collector.schedule,
            "enabled": not is_stub,
            "degraded": is_stub,
            "status": "placeholder" if is_stub else "active",
        }
    return status
