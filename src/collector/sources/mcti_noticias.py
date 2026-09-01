"""IA Brasil — Coletor para notícias do MCTI.

Este módulo implementa a coleta de notícias e publicações do site do
Ministério da Ciência, Tecnologia e Inovação (MCTI).

Uso:
    from src.collector.sources.mcti_noticias import MCTICollector

    collector = MCTICollector()
    news = await collector.fetch_recent_news()
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from loguru import logger

from src.collector.core.fetcher import HTTPFetcher
from src.collector.core.parser.html_parser import HTMLParser
from src.collector.core.parser.rss_parser import RSSParser
from src.collector.core.provenance import ProvenanceTracker


class MCTICollector:
    """Classe para coletar notícias do MCTI.

    Attributes:
        base_url: URL base do site do MCTI
        fetcher: Instância do HTTPFetcher
        html_parser: Instância do HTMLParser
        rss_parser: Instância do RSSParser
        provenance: Instância do ProvenanceTracker
    """

    def __init__(self) -> None:
        self.base_url = "https://www.gov.br/mcti"
        self.fetcher = HTTPFetcher(rate_limit=5, cache_ttl=3600)
        self.html_parser = HTMLParser()
        self.rss_parser = RSSParser()
        self.provenance = ProvenanceTracker()

    async def _fetch_page(self, url: str) -> str:
        """Busca uma página do site do MCTI.

        Args:
            url: URL da página

        Returns:
            Conteúdo HTML da página
        """
        async with self.fetcher as fetcher:
            response = await fetcher.fetch(url)

            if response.status != 200:
                logger.error(f"Error fetching MCTI page: {response.status}")
                raise ValueError(f"MCTI page returned status {response.status}")

            self.provenance.add_record(
                url=url,
                method="GET",
                confidence=0.8,
                metadata={"source": "mcti"},
            )

            return response.data if isinstance(response.data, str) else ""

    async def _try_fetch_rss(self, rss_candidates: list[str]) -> str | None:
        """Tenta buscar conteúdo RSS de uma lista de URLs candidatas.

        Args:
            rss_candidates: Lista de URLs candidatas para o feed RSS

        Returns:
            Conteúdo RSS se encontrado, None caso contrário
        """
        for url in rss_candidates:
            try:
                text = await self._fetch_page(url)
                if text and (
                    text.strip().startswith("<?xml")
                    or "<rss" in text[:500]
                    or "<feed" in text[:500]
                ):
                    return text
            except Exception:
                continue
        return None

    async def fetch_recent_news(self, limit: int = 10) -> list[dict[str, Any]]:
        """Busca notícias recentes do MCTI.

        Tenta feeds RSS candidatos em ordem; se todos falharem,
        faz fallback para scraping HTML.

        Args:
            limit: Número máximo de notícias a buscar

        Returns:
            Lista de notícias com campos title, link, summary, published
        """
        rss_candidates = [
            f"{self.base_url}/pt-br/noticias/rss.xml",
            f"{self.base_url}/pt-br/noticias/rss",
            f"{self.base_url}/feed",
            f"{self.base_url}/rss",
        ]

        rss_content = await self._try_fetch_rss(rss_candidates)
        if rss_content:
            try:
                self.rss_parser.load(rss_content)
                items = self.rss_parser.get_items()
                if items:
                    return items[:limit]
            except Exception as e:
                logger.warning(f"Error parsing RSS content: {e}")

        logger.info("RSS unavailable, falling back to HTML scraping")
        return await self._fetch_news_from_html(limit)

    def _is_relevant_link(self, href: str) -> bool:
        """Verifica se um link é relevante para extração de notícias.

        Args:
            href: URL do link

        Returns:
            True se o link for relevante
        """
        return bool(href) and not href.startswith("#") and not href.startswith("javascript")

    async def _fetch_news_from_url(self, url: str, limit: int) -> list[dict[str, Any]] | None:
        """Tenta extrair notícias de uma URL específica.

        Args:
            url: URL da página
            limit: Número máximo de itens

        Returns:
            Lista de notícias ou None se falhar
        """
        try:
            html_content = await self._fetch_page(url)
            self.html_parser.load(html_content)

            text = self.html_parser.extract_text()
            links = self.html_parser.extract_links()

            # Constrói lista inicial de itens com links filtrados
            items = self._build_link_items(links)

            # Tenta enriquecer com títulos extraídos do HTML
            self._enrich_titles(html_content, items)

            # Preenche lacunas com valores padrão
            self._fill_missing_fields(items, text)

            return items[:limit]
        except Exception as e:
            logger.warning(f"Error fetching news HTML from {url}: {e}")
            return None

    def _build_link_items(self, links: list[str]) -> list[dict[str, Any]]:
        """Constrói itens a partir de links, filtrando irrelevantes.

        Args:
            links: Lista de URLs

        Returns:
            Lista de itens com link preenchido
        """
        seen: set[str] = set()
        items: list[dict[str, Any]] = []
        for link in links:
            if not self._is_relevant_link(link):
                continue
            if link in seen:
                continue
            seen.add(link)
            full_url = link if link.startswith("http") else f"{self.base_url}{link}"
            items.append(
                {
                    "title": "",
                    "link": full_url,
                    "summary": "",
                }
            )
        return items

    def _is_news_like_title(self, title: str) -> bool:
        """Verifica se um título parece ser de uma notícia (vs navegação genérica).

        Args:
            title: Texto do link

        Returns:
            True se parece notícia
        """
        if len(title) < 15:
            return False
        # Ignora navegação genérica
        generic_terms = {
            "ir para",
            "voltar",
            "clique aqui",
            "saiba mais",
            "acesse",
            "página inicial",
            "home",
            "institucional",
            "contato",
            "acessibilidade",
            "mapa do site",
            "termo de uso",
            "privacidade",
        }
        lower = title.lower()
        return not any(term in lower for term in generic_terms)

    def _enrich_titles(self, html_content: str, items: list[dict[str, Any]]) -> None:
        """Tenta extrair títulos de elementos <a> no HTML.

        Args:
            html_content: Conteúdo HTML original
            items: Lista de itens para enriquecer
        """
        self.html_parser.load(html_content)
        soup = self.html_parser.soup
        if not soup:
            return
        for a_tag in soup.find_all("a", href=True):
            raw = a_tag.get("href", "")
            href = str("".join(raw)) if isinstance(raw, list) else str(raw or "")
            if not self._is_relevant_link(href):
                continue
            full_url = href if href.startswith("http") else f"{self.base_url}{href}"
            title = a_tag.get_text(strip=True)
            if self._is_news_like_title(title):
                for item in items:
                    if item["link"] == full_url and not item["title"]:
                        item["title"] = title
                        break

    def _fill_missing_fields(self, items: list[dict[str, Any]], text: str) -> None:
        """Preenche campos vazios com valores padrão.

        Args:
            items: Lista de itens
            text: Texto extraído da página
        """
        for item in items:
            if not item["title"]:
                item["title"] = "Conteúdo MCTI"
            if not item["summary"] and text:
                item["summary"] = text[:100]

    async def _fetch_news_from_html(self, limit: int = 10) -> list[dict[str, Any]]:
        """Busca notícias do HTML da página principal ou de notícias.

        Args:
            limit: Número máximo de notícias a buscar

        Returns:
            Lista de notícias
        """
        news_urls = [
            f"{self.base_url}/pt-br/noticias",
            self.base_url,
        ]

        for url in news_urls:
            result = await self._fetch_news_from_url(url, limit)
            if result is not None:
                return result

        return []

    async def fetch_publications(self, limit: int = 10) -> list[dict[str, Any]]:
        """Busca publicações do MCTI.

        Args:
            limit: Número máximo de publicações a buscar

        Returns:
            Lista de publicações
        """
        publications_url = f"{self.base_url}/publicacoes"

        try:
            html_content = await self._fetch_page(publications_url)
            self.html_parser.load(html_content)

            text = self.html_parser.extract_text()
            links = self.html_parser.extract_links()

            items: list[dict[str, Any]] = []
            seen = set()
            for link in links:
                if not link or link.startswith("#") or link.startswith("javascript"):
                    continue
                if link in seen:
                    continue
                seen.add(link)

                full_url = link if link.startswith("http") else f"{self.base_url}{link}"
                items.append(
                    {
                        "title": f"Publicação {len(items) + 1}",
                        "link": full_url,
                        "summary": text[:100] if text else "",
                    }
                )

            return items[:limit]

        except Exception as e:
            logger.error(f"Error fetching MCTI publications: {e}")
            return []

    async def collect(self) -> list[dict[str, Any]]:
        """Método unificado de coleta.

        Busca notícias e publicações recentes do MCTI e retorna
        uma lista de evidências com campos padronizados.

        Returns:
            Lista de evidências com titulo, descricao, data, fonte_url e tipo
        """
        now = datetime.now(UTC).isoformat()
        all_items: list[dict[str, Any]] = []

        # Coleta notícias
        try:
            news = await self.fetch_recent_news(limit=10)
            for item in news:
                all_items.append(
                    {
                        "titulo": item.get("title", "Notícia MCTI"),
                        "descricao": item.get("summary", item.get("description", "")),
                        "data": item.get("published", now),
                        "fonte_url": item.get("link", self.base_url),
                        "tipo": "noticia",
                    }
                )
        except Exception as e:
            logger.error(f"Error collecting MCTI news: {e}")

        # Coleta publicações
        try:
            publications = await self.fetch_publications(limit=5)
            for item in publications:
                all_items.append(
                    {
                        "titulo": item.get("title", "Publicação MCTI"),
                        "descricao": item.get("summary", item.get("description", "")),
                        "data": now,
                        "fonte_url": item.get("link", self.base_url),
                        # Tipo válido de TipoEvidencia (não existe "publicacao").
                        "tipo": "noticia",
                    }
                )
        except Exception as e:
            logger.error(f"Error collecting MCTI publications: {e}")

        # Registra proveniência
        self.provenance.add_record(
            url=self.base_url,
            method="collect",
            confidence=0.8,
            metadata={
                "source": "mcti",
                "items_count": len(all_items),
                "types": list({i["tipo"] for i in all_items}),
            },
        )

        return all_items

    async def get_provenance_records(self) -> list[dict[str, Any]]:
        """Retorna os registros de proveniência.

        Returns:
            Lista de registros de proveniência
        """
        records = self.provenance.get_records()
        return [record.model_dump() for record in records]
