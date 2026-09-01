"""IA Brasil — Webhooks outbound assinados (issue #1100).

Envio de eventos para URLs externas via POST com assinatura
HMAC-SHA256 no header ``X-Webhook-Signature`` (formato
``sha256=<hexdigest>``, conforme padrão de webhooks assinados).

Configuração (opcional — **inativo por padrão**):
    WEBHOOK_OUTBOUND_URL=https://exemplo.com/hook
    WEBHOOK_OUTBOUND_SECRET=<segredo compartilhado>

Sem as envs, ``enviar_webhook``/dispatchers são no-ops que retornam
``False`` sem fazer nenhuma requisição. Falhas de rede NUNCA interrompem
o fluxo principal — erros são apenas logados.

Eventos suportados:
    - ``acao.status_changed`` (disparado em ScoringService.update_acao_status)
    - ``evidencia.nova`` (disparado em EvidenceService.create_evidencia)

Uso:
    from src.modules.webhook.outbound import notify_status_changed

    await notify_status_changed({"acao_id": "A1", "status": "entregue"})
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
from typing import Any

import httpx
from loguru import logger

DEFAULT_TIMEOUT = 10.0  # segundos (POST com timeout, nunca bloqueia demais)
_SIGNATURE_HEADER = "X-Webhook-Signature"
_EVENT_HEADER = "X-Webhook-Event"


def _hmac_signature(body: bytes, secret: str) -> str:
    """Calcula a assinatura HMAC-SHA256 do corpo da requisição.

    Args:
        body: Corpo serializado (bytes JSON).
        secret: Segredo compartilhado.

    Returns:
        Assinatura no formato ``sha256=<hexdigest>``.
    """
    digest = hmac.new(secret.encode("utf-8"), body, hashlib.sha256).hexdigest()
    return f"sha256={digest}"


def _serialize_payload(payload: dict[str, Any]) -> bytes:
    """Serializa o payload em JSON (compacto, para assinatura + body)."""
    return json.dumps(
        payload,
        ensure_ascii=False,
        separators=(",", ":"),
    ).encode("utf-8")


async def enviar_webhook(
    url: str | None,
    payload: dict[str, Any],
    secret: str | None,
    *,
    event_type: str | None = None,
    timeout: float = DEFAULT_TIMEOUT,
) -> bool:
    """Envia um POST assinado para uma URL externa (best-effort).

    Args:
        url: URL de destino (None desativa o envio).
        payload: Dados do evento (serializados como JSON).
        secret: Segredo para a assinatura HMAC-SHA256.
        event_type: Nome do evento (header ``X-Webhook-Event``), opcional.
        timeout: Timeout do POST em segundos.

    Returns:
        True se o POST retornou status < 400; False se desativado,
        configurado incompletamente ou em caso de erro de rede/HTTP.
    """
    if not url or not secret:
        logger.debug("Webhook outbound inativo — url/secret ausentes")
        return False

    body = _serialize_payload(payload)
    signature = _hmac_signature(body, secret)
    headers: dict[str, str] = {
        "Content-Type": "application/json",
        _SIGNATURE_HEADER: signature,
    }
    if event_type:
        headers[_EVENT_HEADER] = event_type

    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.post(url, content=body, headers=headers)
        if response.status_code >= 400:
            logger.warning(
                "Webhook outbound {} → {} (HTTP {})",
                event_type or "evento",
                url,
                response.status_code,
            )
            return False
        logger.info("Webhook outbound enviado: {} → {}", event_type or "evento", url)
        return True
    except httpx.HTTPError as e:
        logger.warning("Falha ao enviar webhook outbound para {}: {}", url, e)
        return False


def _outbound_config() -> tuple[str | None, str | None]:
    """Lê a configuração de webhook outbound do ambiente.

    Returns:
        Tupla ``(url, secret)`` — ``None`` quando não configurado.
    """
    url = os.getenv("WEBHOOK_OUTBOUND_URL")
    secret = os.getenv("WEBHOOK_OUTBOUND_SECRET")
    return (url or None, secret or None)


async def _dispatch(event_type: str, payload: dict[str, Any]) -> bool:
    """Dispatcher genérico: envia um evento se o webhook estiver configurado."""
    url, secret = _outbound_config()
    if not url or not secret:
        logger.debug("Webhook outbound desativado — ignorando evento '{}'", event_type)
        return False
    return await enviar_webhook(url, payload, secret, event_type=event_type)


async def notify_status_changed(payload: dict[str, Any]) -> bool:
    """Dispara o evento ``acao.status_changed`` (webhook outbound).

    Args:
        payload: Dados da mudança de status (``acao_id``, status, etc.).

    Returns:
        True se enviado; False se inativo ou falhou.
    """
    return await _dispatch("acao.status_changed", payload)


async def notify_evidencia_nova(payload: dict[str, Any]) -> bool:
    """Dispara o evento ``evidencia.nova`` (webhook outbound).

    Args:
        payload: Dados da evidência criada (``evidencia_id``, tipo, etc.).

    Returns:
        True se enviado; False se inativo ou falhou.
    """
    return await _dispatch("evidencia.nova", payload)


__all__ = [
    "_hmac_signature",
    "enviar_webhook",
    "notify_evidencia_nova",
    "notify_status_changed",
]
