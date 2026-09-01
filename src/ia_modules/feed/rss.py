"""IA Brasil — Feed RSS público (RSS 2.0).

Issue #1100 — Engajamento: ``GET /api/v1/feed/rss.xml`` gera um RSS 2.0
válido a partir do feed público existente (eventos, mudanças de status,
evidências e avaliações).

Cada item do feed vira um ``<item>`` do RSS com ``title``, ``link``,
``description``, ``pubDate`` e ``guid``. O XML é gerado apenas com
``xml.etree.ElementTree`` — nenhuma dependência nova.

Uso:
    from src.modules.feed.rss import router

    app.include_router(router, prefix="/api/v1")
"""

from __future__ import annotations

from datetime import UTC, datetime
from email.utils import format_datetime
from typing import TYPE_CHECKING, Any
from xml.etree import ElementTree as ET

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from loguru import logger
from sqlalchemy import select

from src.core.db import Acao
from src.core.db import settings as app_settings
from src.core.limiter import RATE_LIMIT_PUBLIC_READ, limiter
from src.modules.feed.router import _load_unified_feed, get_db

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

router = APIRouter(prefix="/feed", tags=["feed"])

# Quantidade máxima de itens expostos no RSS (título do feed).
RSS_MAX_ITEMS = 50

_CHANNEL_TITLE = "IA Brasil — Feed público do PBIA"
_CHANNEL_DESCRIPTION = (
    "Atividades recentes do monitoramento público do Plano Brasileiro de "
    "Inteligência Artificial (PBIA): eventos, mudanças de status, evidências "
    "e avaliações."
)


# ---------------------------------------------------------------------------
# Utilitários (testáveis sem banco)
# ---------------------------------------------------------------------------


def _rfc2822(value: str) -> str:
    """Converte uma data ISO (``isoformat``) em RFC 2822 (formato do RSS).

    Args:
        value: Data em formato ISO 8601 (com ou sem horário).

    Returns:
        Data formatada em RFC 2822 (ex.: ``Mon, 10 Aug 2026 12:00:00 +0000``).
    """
    if "T" not in value:
        value = f"{value}T00:00:00"
    try:
        dt = datetime.fromisoformat(value)
    except ValueError:
        dt = datetime.now(UTC)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return format_datetime(dt, usegmt=False)


def _item_link(item: dict[str, Any], base_url: str) -> str:
    """Define o ``<link>`` de um item do RSS.

    Prioridade: URL da fonte (evidências), página pública da ação,
    página do feed.

    Args:
        item: Item do feed público (dict normalizado).
        base_url: URL pública da API.

    Returns:
        URL canônica do item.
    """
    fonte_url = item.get("fonte_url")
    if isinstance(fonte_url, str) and fonte_url:
        return fonte_url
    acao_id = item.get("acao_id")
    if isinstance(acao_id, str) and acao_id:
        return f"{base_url}/acoes/{acao_id}"
    return f"{base_url}/feed"


def _append_text(parent: ET.Element, tag: str, text: str) -> None:
    """Adiciona um elemento de texto ao XML (escapa caracteres especiais)."""
    child = ET.SubElement(parent, tag)
    child.text = text


def build_rss(
    items: list[dict[str, Any]],
    base_url: str,
    *,
    channel_title: str = _CHANNEL_TITLE,
    channel_description: str = _CHANNEL_DESCRIPTION,
) -> str:
    """Constrói o documento RSS 2.0 a partir dos itens do feed público.

    Função pura (sem I/O) — testável sem banco. Usa ``xml.etree`` para
    garantir o escape correto de caracteres especiais em títulos e
    descrições.

    Args:
        items: Itens normalizados do feed público (título/descrição já
            redigidos de PII pelo loader).
        base_url: URL pública da API (base dos links).
        channel_title: Título do canal.
        channel_description: Descrição do canal.

    Returns:
        Documento XML serializado como string (com declaração XML).
    """
    rss = ET.Element("rss", {"version": "2.0", "xmlns:atom": "http://www.w3.org/2005/Atom"})
    channel = ET.SubElement(rss, "channel")

    _append_text(channel, "title", channel_title)
    _append_text(channel, "link", f"{base_url}/feed")
    _append_text(channel, "description", channel_description)
    _append_text(channel, "language", "pt-br")

    ET.SubElement(
        channel,
        "atom:link",
        {
            "href": f"{base_url}/api/v1/feed/rss.xml",
            "rel": "self",
            "type": "application/rss+xml",
        },
    )

    if items:
        _append_text(channel, "lastBuildDate", _rfc2822(str(items[0]["data"])))

    for item in items:
        entry = ET.SubElement(channel, "item")
        _append_text(entry, "title", str(item["titulo"]))
        _append_text(entry, "link", _item_link(item, base_url))
        _append_text(entry, "description", str(item["descricao"]))
        _append_text(entry, "pubDate", _rfc2822(str(item["data"])))
        guid = ET.SubElement(entry, "guid", {"isPermaLink": "false"})
        guid.text = str(item["id"])

    return ET.tostring(rss, encoding="unicode", xml_declaration=True)


# ---------------------------------------------------------------------------
# Endpoint público
# ---------------------------------------------------------------------------


@router.get("/rss.xml", include_in_schema=False)
@limiter.limit(RATE_LIMIT_PUBLIC_READ)
async def feed_rss(
    request: Request,
    session: AsyncSession = Depends(get_db),
) -> Response:
    """Gera o feed RSS 2.0 público (issue #1100).

    Returns:
        ``application/rss+xml`` com os últimos ``RSS_MAX_ITEMS`` itens do
        feed público.
    """
    try:
        acoes_result = await session.execute(select(Acao.id, Acao.nome))
        acoes_map: dict[str, str] = {row[0]: row[1] for row in acoes_result}
        items = await _load_unified_feed(
            session,
            acoes_map,
            offset=0,
            limit=RSS_MAX_ITEMS,
        )
        xml = build_rss(items, app_settings.public_api_url.rstrip("/"))
    except Exception:
        logger.error("Erro ao gerar RSS público", exc_info=True)
        raise HTTPException(status_code=500, detail="Erro ao gerar feed RSS")
    return Response(
        content=xml,
        media_type="application/rss+xml",
        headers={
            "Cache-Control": "public, max-age=600",
            "Content-Disposition": 'inline; filename="feed.xml"',
        },
    )


__all__ = ["_item_link", "_rfc2822", "build_rss", "router"]
