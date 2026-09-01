"""IA Brasil — Coletor para Diário Oficial da União (DOU).

Este módulo implementa a coleta de dados do Diário Oficial da União
através de scraping de páginas web.

Uso:
    from src.collector.sources.dou_scraper import DOUScraper

    scraper = DOUScraper()
    data = await scraper.scrape_section(1, date="2025-01-01")
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

from loguru import logger

from src.collector.core.fetcher import HTTPFetcher
from src.collector.core.parser.html_parser import HTMLParser
from src.collector.core.provenance import ProvenanceTracker


class DOUScraper:
    """Classe para coletar dados do Diário Oficial da União.

    Attributes:
        base_url: URL base do DOU
        fetcher: Instância do HTTPFetcher
        parser: Instância do HTMLParser
        provenance: Instância do ProvenanceTracker
    """

    # Versão do parser/coletor (registrada no IngestionRun — issue #1087).
    PARSER_VERSION = "1.1.0"

    def __init__(self) -> None:
        self.base_url = "https://www.in.gov.br"
        self.consulta_url = f"{self.base_url}/consulta"
        self.fetcher = HTTPFetcher(rate_limit=1, cache_ttl=86400, timeout=15)
        self.parser = HTMLParser()
        self.provenance = ProvenanceTracker()

    async def _fetch_page(self, url: str) -> str | None:
        """Busca uma página do DOU.

        Args:
            url: URL da página

        Returns:
            Conteúdo HTML da página ou None se falhar
        """
        try:
            async with self.fetcher as fetcher:
                response = await fetcher.fetch(url)

                if response.status != 200:
                    logger.warning(f"DOU page returned status {response.status}: {url}")
                    return None

                self.provenance.add_record(
                    url=url,
                    method="GET",
                    confidence=0.8,
                    metadata={"source": "dou"},
                )

                return response.data if isinstance(response.data, str) else ""
        except Exception as e:
            logger.warning(f"Error fetching DOU page {url}: {e}")
            return None

    async def _try_leitura(self, section: int, date: str) -> str | None:
        """Tenta buscar matéria via endpoint de leitura do DOU.

        Args:
            section: Seção do DOU (1, 2 ou 3)
            date: Data no formato YYYY-MM-DD

        Returns:
            Conteúdo HTML ou None se falhar
        """
        leitura_url = f"{self.base_url}/leitura/jornal/{date}/secao/{section}"
        html = await self._fetch_page(leitura_url)
        if html is not None and len(html.strip()) > 100:
            return html
        return None

    async def _try_search(self, date: str) -> str | None:
        """Tenta buscar matérias via busca do DOU.

        Args:
            date: Data no formato YYYY-MM-DD

        Returns:
            Conteúdo HTML ou None se falhar
        """
        search_url = f"{self.consulta_url}?dataPublicacaoInicial={date}&dataPublicacaoFinal={date}"
        html = await self._fetch_page(search_url)
        if html is not None and len(html.strip()) > 100:
            return html
        return None

    async def scrape_section(
        self,
        section: int,
        date: str,
        trecho_chars: int = 1500,
    ) -> list[dict[str, Any]]:
        """Extrai dados de uma seção do DOU.

        Tenta múltiplos endpoints em ordem decrescente de especificidade.

        Args:
            section: Seção do DOU (1, 2 ou 3)
            date: Data no formato YYYY-MM-DD
            trecho_chars: Tamanho máximo do trecho de texto retornado por
                matéria. Quando o corpo excede o limite, o item é marcado
                com ``trecho_truncado=True``.

        Returns:
            Lista de itens extraídos

        Raises:
            ValueError: Se a seção for inválida
        """
        if section not in [1, 2, 3]:
            raise ValueError("Section must be 1, 2, or 3")

        html_content = await self._try_leitura(section, date)
        if html_content is None:
            html_content = await self._try_search(date)

        if html_content is None:
            logger.warning(f"Could not fetch DOU data for section {section} on {date}")
            return []

        self.parser.load(html_content)
        text = self.parser.extract_text()
        metadata = self.parser.extract_metadata()
        links = self.parser.extract_links()

        # Tenta extrair matérias individuais do HTML
        soup = self.parser.soup
        items: list[dict[str, Any]] = []
        if soup:
            article_selectors = [
                "article",
                "div.artigo",
                "div.texto-dou",
                "div[class*=materia]",
                "li.artigo",
            ]
            articles: list[Any] = []
            for selector in article_selectors:
                articles = soup.select(selector)
                if articles:
                    break

            if articles:
                for article in articles:
                    title_el = article.find(["h1", "h2", "h3", "h4", "strong", "a"])
                    title = title_el.get_text(strip=True) if title_el else ""
                    body = article.get_text(separator="\n", strip=True)
                    if len(body) < 20:
                        continue
                    items.append(
                        {
                            "section": section,
                            "date": date,
                            "title": title or f"DOU Seção {section} - {date}",
                            "text": body[:trecho_chars],
                            "trecho_truncado": len(body) > trecho_chars,
                        }
                    )

        if not items:
            # Fallback: retorna dados genéricos da página
            page_text = text[:trecho_chars] if text else ""
            items.append(
                {
                    "section": section,
                    "date": date,
                    "title": f"Diário Oficial - Seção {section} - {date}",
                    "text": page_text,
                    "trecho_truncado": bool(text) and len(text) > trecho_chars,
                    "metadata": metadata,
                    "links": links[:10],
                }
            )

        return items

    async def scrape_recent(
        self,
        section: int = 1,
        days: int = 7,
        trecho_chars: int = 1500,
    ) -> list[dict[str, Any]]:
        """Extrai dados recentes de uma ou mais seções do DOU.

        Args:
            section: Seção do DOU (1, 2 ou 3). Padrão: 1.
            days: Número de dias a considerar. Padrão: 7.
            trecho_chars: Tamanho máximo do trecho de texto por matéria.

        Returns:
            Lista de itens extraídos
        """
        today = datetime.now()
        results: list[dict[str, Any]] = []

        for i in range(days):
            date = (today - timedelta(days=i)).strftime("%Y-%m-%d")
            try:
                items = await self.scrape_section(section, date, trecho_chars=trecho_chars)
                results.extend(items)
            except Exception as e:
                logger.warning(f"Error scraping DOU section {section} for {date}: {e}")

        return results

    async def collect(self, trecho_chars: int = 1500) -> list[dict[str, Any]]:
        """Método unificado de coleta.

        Extrai matérias das seções 1 e 2 do DOU dos últimos 3 dias
        e retorna uma lista de evidências com campos padronizados.

        Args:
            trecho_chars: Tamanho máximo do trecho de texto por matéria.
                Padrão: 1500.

        Returns:
            Lista de evidências com titulo, descricao, data, fonte_url e tipo
        """
        all_items: list[dict[str, Any]] = []
        sections = [1, 2]
        days_back = 3
        today = datetime.now()

        for section in sections:
            for i in range(days_back):
                date = (today - timedelta(days=i)).strftime("%Y-%m-%d")
                try:
                    items = await self.scrape_section(section, date, trecho_chars=trecho_chars)
                    for item in items:
                        all_items.append(
                            {
                                "titulo": item.get("title", f"DOU Seção {section}"),
                                "descricao": item.get("text", item.get("summary", "")),
                                "data": date,
                                "fonte_url": f"{self.base_url}/leitura/jornal/{date}/secao/{section}",  # noqa: E501
                                "tipo": f"dou_secao_{section}",
                                "metadata": {
                                    "trecho_truncado": item.get("trecho_truncado", False),
                                    "trecho_chars": trecho_chars,
                                },
                            }
                        )
                except Exception as e:
                    logger.warning(f"Error collecting DOU section {section} for {date}: {e}")

        self.provenance.add_record(
            url=self.consulta_url,
            method="collect",
            confidence=0.8,
            metadata={
                "source": "dou",
                "items_count": len(all_items),
                "sections": sections,
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
