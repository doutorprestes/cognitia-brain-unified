"""IA Brasil — Webhook Router.

Endpoint público (protegido por segredo) para atualização periódica
de dados do DOU via webhook.

Uso:
    GET /api/v1/webhook/dou-update
    Header: X-Webhook-Secret: <segredo>
"""

from __future__ import annotations

import os
from typing import Any

from fastapi import APIRouter, Header, HTTPException, Request
from loguru import logger

from src.core.limiter import RATE_LIMIT_WRITE, limiter

router = APIRouter(prefix="/webhook", tags=["webhook"])

_WEBHOOK_SECRET = os.getenv("WEBHOOK_SECRET", "")


def _check_secret(secret: str | None) -> bool:
    """Valida o segredo do webhook (fail-closed).

    Sem WEBHOOK_SECRET configurado, nunca aceita o segredo.
    """
    if not _WEBHOOK_SECRET:
        return False
    return secret == _WEBHOOK_SECRET


@router.get("/dou-update", include_in_schema=False)
@limiter.limit(RATE_LIMIT_WRITE)
async def trigger_dou_update(
    request: Request,
    x_webhook_secret: str | None = Header(default=None, alias="X-Webhook-Secret"),
) -> dict[str, Any]:
    """Trigger atualização do DOU via webhook.

    Protegido por segredo compartilhado via header X-Webhook-Secret.
    Fail-closed: sem WEBHOOK_SECRET configurado, não processa.

    Args:
        x_webhook_secret: Segredo compartilhado (header)

    Returns:
        Status da execução
    """
    if not _check_secret(x_webhook_secret):
        raise HTTPException(
            status_code=403,
            detail="Segredo inválido ou não configurado",
        )

    try:
        from src.collector.scheduler import CollectorScheduler

        scheduler = CollectorScheduler()
        result = await scheduler.run_source("dou")

        logger.info("Webhook DOU update triggered: status={}", result.get("status", "unknown"))

        return {
            "status": "ok",
            "source": "dou",
            "result": result,
        }
    except Exception as exc:
        logger.error("Erro no webhook DOU: {}", exc, exc_info=True)
        raise HTTPException(
            status_code=500,
            detail={"message": "Erro ao executar atualização do DOU", "error": str(exc)},
        ) from exc
