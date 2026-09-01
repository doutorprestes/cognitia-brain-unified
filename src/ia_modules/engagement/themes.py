"""IA Brasil — Temas de engajamento assináveis (issue #1100).

Lista documentada de temas/eventos que podem ser "assinados" por canal.
Atualmente há apenas o canal Telegram, ativado por opt-in via env:

    ENGAGEMENT_TELEGRAM_THEMES=status_acao,evidencia_nova   (CSV)

Sem temas configurados (env ausente), ``notify_subscribers`` é um no-op
(inativo por padrão). O envio usa o ``Notifier`` Telegram existente
(``src/collector/notification.py``) — nenhuma infra de subscription é
inventada nesta entrega (mínimo viável).

Uso:
    from src.modules.engagement.themes import TEMAS_ASSINAVEIS, notify_subscribers

    await notify_subscribers("status_acao", {"acao": "A1", "status": "entregue"})
"""

from __future__ import annotations

import os
from typing import Any

from loguru import logger

from src.collector.notification import Notifier

# Lista canônica de temas assináveis — documentação pública do endpoint
# ``GET /api/v1/engagement/temas``.
TEMAS_ASSINAVEIS: list[dict[str, str]] = [
    {
        "tema": "status_acao",
        "evento": "acao.status_changed",
        "descricao": "Mudança de status de uma ação do PBIA",
    },
    {
        "tema": "evidencia_nova",
        "evento": "evidencia.nova",
        "descricao": "Nova evidência ingerida no portal",
    },
    {
        "tema": "qualidade",
        "evento": "qualidade.alertas",
        "descricao": "Alertas de qualidade de dados por fonte",
    },
]


def temas_assinaveis() -> list[dict[str, str]]:
    """Retorna a lista pública de temas assináveis (cópia defensiva)."""
    return [dict(item) for item in TEMAS_ASSINAVEIS]


def _temas_configurados() -> set[str]:
    """Lê ``ENGAGEMENT_TELEGRAM_THEMES`` (CSV) e retorna os temas ativos.

    Returns:
        Conjunto de temas configurados (vazio = inativo).
    """
    raw = os.getenv("ENGAGEMENT_TELEGRAM_THEMES", "")
    return {item.strip() for item in raw.split(",") if item.strip()}


def _format_tema_message(tema: str, payload: dict[str, Any]) -> str:
    """Formata a mensagem Telegram de um tema de engajamento.

    Args:
        tema: Chave do tema (ex.: ``status_acao``).
        payload: Dados do evento (pares chave/valor).

    Returns:
        Mensagem em Markdown para o Telegram.
    """
    lines = [f"🔔 *IA Brasil — {tema}*", ""]
    for key, value in payload.items():
        lines.append(f"*{key}:* {value}")
    return "\n".join(lines)


async def notify_subscribers(tema: str, payload: dict[str, Any]) -> bool:
    """Notifica assinantes de um tema via Telegram (opt-in por env).

    Args:
        tema: Chave do tema (deve estar em ``ENGAGEMENT_TELEGRAM_THEMES``).
        payload: Dados do evento serializados na mensagem.

    Returns:
        True se a notificação foi enviada; False quando o tema não está
        configurado, o Telegram está desativado ou o envio falhou.
    """
    if tema not in _temas_configurados():
        logger.debug("Engagement: tema '{}' não assinado (ENGAGEMENT_TELEGRAM_THEMES)", tema)
        return False

    notifier = Notifier.from_env()
    if not notifier.enabled:
        logger.debug("Engagement inativo — Telegram não configurado")
        return False

    message = _format_tema_message(tema, payload)
    return await notifier.notify_tema(tema, message)


__all__ = ["TEMAS_ASSINAVEIS", "notify_subscribers", "temas_assinaveis"]
