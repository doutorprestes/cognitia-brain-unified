"""Router para endpoints de saúde do pipeline."""

from __future__ import annotations

import os
from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from pydantic import BaseModel
from sqlalchemy.exc import IntegrityError
from src.core.limiter import RATE_LIMIT_ADMIN, limiter
from src.modules.auth.dependencies import get_admin_api_key
from src.modules.pipeline_health.schemas import PipelineHealth
from src.modules.pipeline_health.service import PipelineHealthService

router = APIRouter(prefix="/sdlc", tags=["admin"])

# In-memory store for CI results (last 100 runs)
_ci_results: list[dict[str, Any]] = []

_WEBHOOK_SECRET = os.getenv("WEBHOOK_SECRET", "")


class CIResultsRequest(BaseModel):
    """Schema for CI results submission."""

    pr: int | None = None
    timestamp: str
    duration_seconds: float
    passed: bool
    coverage: float
    checks: dict[str, object]


def _check_ci_secret(secret: str | None) -> bool:
    """Valida o segredo do webhook de CI (fail-closed).

    Sem WEBHOOK_SECRET configurado, nunca aceita o segredo.
    """
    if not _WEBHOOK_SECRET:
        return False
    return secret == _WEBHOOK_SECRET


@router.get("/pipeline-health", response_model=PipelineHealth)
@limiter.limit(RATE_LIMIT_ADMIN)
async def get_pipeline_health(
    request: Request,
    _role: str = Depends(get_admin_api_key),
) -> PipelineHealth:
    """Retorna status de saúde do pipeline SDLC.

    Verifica:
    - Runners busy
    - Jobs na fila
    - Issues abertas
    - Status geral do CI

    Requer role: admin.
    """
    return await PipelineHealthService.get_health()


@router.get("/pipeline-health/runs")
@limiter.limit(RATE_LIMIT_ADMIN)
async def get_pipeline_runs(
    request: Request,
    _role: str = Depends(get_admin_api_key),
) -> list[dict[str, Any]]:
    """Retorna ultimos workflows executados. Requer role: admin."""
    return await PipelineHealthService.get_recent_runs()


@router.post("/ci-results")
@limiter.limit(RATE_LIMIT_ADMIN)
async def receive_ci_results(
    request: Request,
    payload: CIResultsRequest,
    _role: str = Depends(get_admin_api_key),
    x_webhook_secret: str | None = Header(default=None, alias="X-Webhook-Secret"),
) -> dict[str, Any]:
    """Receive CI results from local runner.

    Requer role: admin e segredo de webhook válido via header
    X-Webhook-Secret. Sem WEBHOOK_SECRET configurado, falha fechado.
    """
    if not _check_ci_secret(x_webhook_secret):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Segredo de webhook inválido ou não configurado.",
        )

    try:
        result = payload.model_dump()
        _ci_results.append(result)
        # Keep only last 100
        if len(_ci_results) > 100:
            _ci_results.pop(0)

        return {
            "status": "received",
            "passed": payload.passed,
            "coverage": payload.coverage,
            "total_results": len(_ci_results),
        }
    except IntegrityError:
        raise HTTPException(
            status_code=409,
            detail="Conflito: registro duplicado ou violação de restrição",
        )


@router.get("/ci-results")
@limiter.limit(RATE_LIMIT_ADMIN)
async def get_ci_results(
    request: Request,
    _role: str = Depends(get_admin_api_key),
) -> list[dict[str, Any]]:
    """Get recent CI results. Requer role: admin."""
    return _ci_results[-20:] if _ci_results else []


@router.get("/ci-results/latest")
@limiter.limit(RATE_LIMIT_ADMIN)
async def get_latest_ci_result(
    request: Request,
    _role: str = Depends(get_admin_api_key),
) -> dict[str, Any] | None:
    """Get latest CI result. Requer role: admin."""
    return _ci_results[-1] if _ci_results else None
