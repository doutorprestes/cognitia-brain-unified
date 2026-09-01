"""IA Brasil — Módulo de engajamento (issue #1100).

Endpoints públicos:
- ``GET /api/v1/engagement/temas`` — temas/eventos assináveis (documentação).
- ``GET /api/v1/engagement/fontes`` — catálogo público de fontes de coleta
  (registry + runs: periodicidade, última coleta, status, falhas, custo, valor).

O envio de alertas por tema (Telegram) é opt-in via
``ENGAGEMENT_TELEGRAM_THEMES`` e implementado em ``themes.py``; o catálogo
de fontes vive em ``fontes.py``.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request
from loguru import logger

from src.core.limiter import RATE_LIMIT_PUBLIC_READ, limiter
from src.modules.engagement.fontes import FonteCatalogo, get_catalogo_fontes
from src.modules.engagement.themes import temas_assinaveis

router = APIRouter(prefix="/engagement", tags=["engagement"])


@router.get("/temas", response_model=list[dict[str, str]])
@limiter.limit(RATE_LIMIT_PUBLIC_READ)
async def listar_temas(request: Request) -> list[dict[str, str]]:
    """Lista temas/eventos assináveis (documentação pública, issue #1100).

    Os temas só geram notificações quando habilitados via env
    ``ENGAGEMENT_TELEGRAM_THEMES`` (CSV) — inativo por padrão.
    """
    return temas_assinaveis()


@router.get("/fontes", response_model=list[FonteCatalogo])
@limiter.limit(RATE_LIMIT_PUBLIC_READ)
async def catalogo_fontes(request: Request) -> list[FonteCatalogo]:
    """Catálogo público de fontes de coleta (issue #1100).

    Lista as fontes do ``config/sources.yaml`` com periodicidade, última
    coleta, status do último run, falhas consecutivas, custo estimado
    (None quando desconhecido — nunca inventado) e valor declarado.
    """
    try:
        return await get_catalogo_fontes()
    except Exception:
        logger.error("Erro ao gerar catálogo de fontes", exc_info=True)
        raise HTTPException(status_code=500, detail="Erro ao gerar catálogo de fontes")


__all__ = ["router"]
