"""IA Brasil — Parser para feeds RSS.

Este módulo fornece funcionalidades para extrair dados de feeds RSS.

Uso:
    from src.collector.core.parser.rss_parser import RSSParser

    parser = RSSParser()
    parser.load(rss_content)
    items = parser.get_items()
"""

from __future__ import annotations

from typing import Any

import feedparser
from loguru import logger


class RSSParser:
    """Classe para extrair dados de feeds RSS.

    Attributes:
        feed: Dados do feed RSS
    """

    def __init__(self) -> None:
        self.feed: feedparser.FeedParserDict | None = None

    def load(self, rss_content: str) -> None:
        """Carrega conteúdo RSS.

        Args:
            rss_content: Conteúdo RSS

        Raises:
            feedparser.FeedParserError: Se o conteúdo não for um feed RSS válido
        """
        try:
            self.feed = feedparser.parse(rss_content)
        except Exception:
            logger.error("Invalid RSS content")
            raise

    def get_items(self) -> list[dict[str, Any]]:
        """Retorna os itens do feed RSS.

        Returns:
            Lista de itens

        Raises:
            RuntimeError: Se nenhum feed RSS estiver carregado
        """
        if not self.feed:
            raise RuntimeError("No RSS feed loaded")

        items = []
        for entry in self.feed.entries:
            item = {
                "title": entry.get("title", ""),
                "link": entry.get("link", ""),
                "summary": entry.get("summary", ""),
                "published": entry.get("published", ""),
            }
            items.append(item)

        return items

    def get_feed_metadata(self) -> dict[str, Any]:
        """Retorna os metadados do feed RSS.

        Returns:
            Dicionário com metadados

        Raises:
            RuntimeError: Se nenhum feed RSS estiver carregado
        """
        if not self.feed:
            raise RuntimeError("No RSS feed loaded")

        return {
            "title": self.feed.feed.get("title", ""),
            "link": self.feed.feed.get("link", ""),
            "description": self.feed.feed.get("description", ""),
            "language": self.feed.feed.get("language", ""),
        }

    def get_item_count(self) -> int:
        """Retorna o número de itens no feed RSS.

        Returns:
            Número de itens

        Raises:
            RuntimeError: Se nenhum feed RSS estiver carregado
        """
        if not self.feed:
            raise RuntimeError("No RSS feed loaded")
        return len(self.feed.entries) if self.feed.entries else 0
