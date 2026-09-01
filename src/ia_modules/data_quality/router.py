"""Router para qualidade de dados — IA Brasil.

Endpoints para:
- Health check de frescor dos dados
- Relatório público de qualidade (score por fonte + checks)
- Alertas ativos de qualidade
- Métricas de qualidade
- Validação de dados

Endpoints públicos: health/data-freshness, quality, alerts
Endpoints autenticados: quality/metrics, quality/validate
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.exc import IntegrityError

from src.core.limiter import RATE_LIMIT_AUTHENTICATED, RATE_LIMIT_PUBLIC_READ, limiter
from src.modules.auth.dependencies import get_contributor_api_key
from src.modules.data_quality.schemas import (
    DataQualityMetrics,
    HealthDataFreshnessResponse,
    QualityAlert,
    QualityReportResponse,
    ValidationResult,
)
from src.modules.data_quality.service import DataQualityService

router = APIRouter(prefix="/data-quality", tags=["data-quality"])


@router.get(
    "/health/data-freshness",
    response_model=HealthDataFreshnessResponse,
    tags=["health"],
)
@limiter.limit(RATE_LIMIT_AUTHENTICATED)
async def health_data_freshness(request: Request) -> HealthDataFreshnessResponse:
    """Verifica frescor dos dados de todas as fontes.

    Retorna status geral (healthy/degraded/critical) com base
    na última data de coleta e falhas consecutivas por fonte.

    Status:
        - healthy: todas as fontes com dados recentes
        - degraded: alguma fonte desatualizada (>14 dias)
        - critical: fonte com >=3 falhas consecutivas
    """
    return await DataQualityService.get_health_data_freshness()


@router.get(
    "/quality",
    response_model=QualityReportResponse,
    tags=["health"],
)
@limiter.limit(RATE_LIMIT_PUBLIC_READ)
async def get_public_quality_report(request: Request) -> QualityReportResponse:
    """Relatório público de qualidade dos dados (score por fonte).

    Retorna, para cada fonte/dataset, score 0-100 com severidade
    (healthy/degraded/critical) e checks detalhados de volume, frescor,
    drift de schema (parser_version) e quarentena (runs partial).

    Sem dados sensíveis: apenas agregados e metadados de ingestão.
    """
    return await DataQualityService.get_quality_report()


@router.get(
    "/alerts",
    response_model=list[QualityAlert],
    tags=["health"],
)
@limiter.limit(RATE_LIMIT_PUBLIC_READ)
async def get_active_alerts(request: Request) -> list[QualityAlert]:
    """Retorna alertas ativos de qualidade de dados.

    Alertas são gerados a partir do relatório de qualidade quando
    ``DQ_ALERTS_ENABLED=true`` (default). Configuráveis via env.
    """
    return await DataQualityService.evaluate_alerts()


@router.get(
    "/quality/metrics",
    response_model=DataQualityMetrics,
)
@limiter.limit(RATE_LIMIT_AUTHENTICATED)
async def get_quality_metrics(
    request: Request,
    _role: str = Depends(get_contributor_api_key),
) -> DataQualityMetrics:
    """Retorna métricas agregadas de qualidade dos dados.

    Inclui contagens de entidades, distribuição de status,
    valor total orçamentário e violações de integridade.
    """
    return await DataQualityService.get_quality_metrics()


@router.get(
    "/quality/validate",
    response_model=ValidationResult,
)
@limiter.limit(RATE_LIMIT_AUTHENTICATED)
async def run_validation(
    request: Request,
    _role: str = Depends(get_contributor_api_key),
) -> ValidationResult:
    """Executa todas as validações de qualidade e retorna resultado.

    Validações executadas:
    - Schema: campos obrigatórios preenchidos
    - Integridade referencial: FKs válidas
    - Consistência: execução vs meta orçamentária do exercício (config)
    - Ações sem status definido
    """
    try:
        return await DataQualityService.run_full_validation()
    except IntegrityError:
        raise HTTPException(
            status_code=409,
            detail="Conflito: registro duplicado ou violação de restrição",
        )
