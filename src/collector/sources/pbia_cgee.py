"""IA Brasil — Coletor para o site público do PBIA/CGEE.

Monitora o site oficial do Plano Brasileiro de Inteligência Artificial
(http://pbia.cgee.org.br) para detectar alterações via HTTP polling.

Não requer chave de API — apenas faz requisições HTTP e analisa
<meta> tags, cabeçalhos e conteúdo textual para detectar mudanças
no plano, novas versões ou atualizações.

Uso:
    from src.collector.sources.pbia_cgee import PbiaCgeeCollector

    collector = PbiaCgeeCollector()
    result = await collector.collect()
"""

from __future__ import annotations

import hashlib
from datetime import datetime
from typing import Any

from loguru import logger

from src.collector.core.fetcher import HTTPFetcher
from src.collector.core.provenance import ProvenanceTracker

# Constantes
PBIA_BASE_URL = "https://pbia.cgee.org.br"
PBIA_DOC_URL = f"{PBIA_BASE_URL}/documento-oficial"
PBIA_ABOUT_URL = f"{PBIA_BASE_URL}/sobre"

# Meta tags que indicam versão do documento
RELEVANT_META_NAMES = [
    "description",
    "keywords",
    "application-name",
    "generator",
    "version",
    "modified",
    "last-modified",
    "revised",
]


class PbiaCgeeCollector:
    """Coletor para o site público do PBIA/CGEE.

    Realiza polling periódico do site oficial do PBIA, analisando
    meta tags, cabeçalhos HTTP e conteúdo para detectar mudanças.

    Attributes:
        base_url: URL base do site PBIA
        fetcher: Instância do HTTPFetcher para requisições
        provenance: Instância do ProvenanceTracker
    """

    def __init__(self) -> None:
        self.base_url = PBIA_BASE_URL
        self.fetcher = HTTPFetcher(rate_limit=2, cache_ttl=600)
        self.provenance = ProvenanceTracker()

    async def fetch_page(self, url: str) -> dict[str, Any]:
        """Busca uma página do site PBIA.

        Args:
            url: URL completa da página

        Returns:
            Dict com status, headers, meta tags, texto extraído e hash
        """
        async with self.fetcher as fetcher:
            response = await fetcher.fetch(url, use_cache=False)

            status = response.status
            headers = response.headers
            raw_data: str = response.data if isinstance(response.data, str) else ""

            # Extrair meta tags do HTML
            meta_tags = self._extract_meta_tags(raw_data)

            # Extrair title
            title = self._extract_title(raw_data)

            # Hash do conteúdo bruto (para detecção de mudanças)
            content_hash = hashlib.sha256(raw_data.encode()).hexdigest()

            result = {
                "url": url,
                "status": status,
                "timestamp": datetime.now().isoformat(),
                "title": title,
                "meta_tags": meta_tags,
                "content_hash": content_hash,
                "content_length": len(raw_data),
                "headers": {
                    "content-type": headers.get("content-type", ""),
                    "last-modified": headers.get("last-modified", ""),
                    "etag": headers.get("etag", ""),
                    "content-length": headers.get("content-length", ""),
                },
            }

            self.provenance.add_record(
                url=url,
                method="GET",
                confidence=0.85,
                metadata={
                    "status": status,
                    "content_hash": content_hash[:16],
                    "content_length": len(raw_data),
                },
            )

            return result

    def _extract_meta_tags(self, html: str) -> dict[str, str]:
        """Extrai meta tags relevantes do HTML.

        Args:
            html: Conteúdo HTML da página

        Returns:
            Dict com nome → conteúdo das meta tags
        """
        meta_tags: dict[str, str] = {}

        for meta_name in RELEVANT_META_NAMES:
            # <meta name="..." content="...">
            pattern_start = f'<meta name="{meta_name}"'
            if pattern_start not in html.lower():
                pattern_start = f"<meta name='{meta_name}'"
                if pattern_start not in html.lower():
                    continue

            # Procurar content= após o name
            idx = html.lower().find(pattern_start)
            if idx == -1:
                continue

            content_section = html[idx : idx + 500]
            content_start = content_section.find('content="')
            if content_start == -1:
                content_start = content_section.find("content='")
                if content_start == -1:
                    continue
                content_start += len("content='")
                content_end = content_section.find("'", content_start)
            else:
                content_start += len('content="')
                content_end = content_section.find('"', content_start)

            if content_start >= 0 and content_end > content_start:
                value = content_section[content_start:content_end]
                meta_tags[meta_name] = value

        return meta_tags

    def _extract_title(self, html: str) -> str:
        """Extrai o título <title> do HTML.

        Args:
            html: Conteúdo HTML da página

        Returns:
            Título da página ou string vazia
        """
        title_start = html.lower().find("<title>")
        if title_start == -1:
            return ""
        title_start += len("<title>")
        title_end = html.lower().find("</title>", title_start)
        if title_end == -1:
            return html[title_start:].strip()[:200]
        return html[title_start:title_end].strip()

    async def check_for_updates(
        self,
        previous_hash: str | None = None,
    ) -> dict[str, Any]:
        """Verifica se houve alterações no site desde a última checagem.

        Args:
            previous_hash: Hash SHA-256 da última versão conhecida

        Returns:
            Dict com resultado da verificação:
            - changed: bool se houve mudança
            - current_hash: hash atual
            - previous_hash: hash anterior
            - details: detalhes da página
        """
        page_data = await self.fetch_page(PBIA_DOC_URL)

        current_hash = page_data["content_hash"]
        changed = previous_hash is not None and current_hash != previous_hash

        return {
            "changed": changed,
            "current_hash": current_hash,
            "previous_hash": previous_hash,
            "page": page_data,
            "checked_at": datetime.now().isoformat(),
        }

    async def collect(self) -> list[dict[str, Any]]:
        """Método unificado de coleta.

        Busca as páginas principais do site PBIA e retorna
        evidências padronizadas.

        Returns:
            Lista de evidências com titulo, descricao, data, fonte_url e tipo
        """
        results: list[dict[str, Any]] = []

        pages_to_check = [
            ("Página Inicial", PBIA_BASE_URL),
            ("Documento Oficial", PBIA_DOC_URL),
            ("Sobre", PBIA_ABOUT_URL),
        ]

        for page_name, url in pages_to_check:
            try:
                page_data = await self.fetch_page(url)

                if page_data["status"] != 200:
                    logger.warning(f"PBIA page {url} returned status {page_data['status']}")
                    results.append(
                        {
                            "titulo": f"PBIA: {page_name} (erro)",
                            "descricao": (
                                f"Página {page_name} do PBIA retornou status {page_data['status']}"
                            ),
                            "data": datetime.now().isoformat(),
                            "fonte_url": url,
                            "tipo": "pagina_institucional",
                            "content_hash": page_data["content_hash"],
                            "meta_tags": page_data["meta_tags"],
                        }
                    )
                    continue

                # Construir descrição baseada em título e meta tags
                meta_desc = page_data["meta_tags"].get("description", "")
                descricao = meta_desc or (
                    f"Conteúdo da página {page_name} do site oficial do PBIA ({url})"
                )

                results.append(
                    {
                        "titulo": (page_data["title"] or f"PBIA: {page_name}"),
                        "descricao": descricao,
                        "data": datetime.now().isoformat(),
                        "fonte_url": url,
                        "tipo": "pagina_institucional",
                        "content_hash": page_data["content_hash"],
                        "meta_tags": page_data["meta_tags"],
                    }
                )

                logger.debug(
                    f"PBIA: {page_name} coletada — hash={page_data['content_hash'][:16]}..."
                )

            except Exception as e:
                logger.error(f"Erro ao coletar página PBIA {url}: {e}")
                results.append(
                    {
                        "titulo": f"PBIA: {page_name} (falha)",
                        "descricao": f"Falha ao coletar {url}: {e!s}",
                        "data": datetime.now().isoformat(),
                        "fonte_url": url,
                        "tipo": "outro",
                        "content_hash": "",
                        "meta_tags": {},
                    }
                )

        self.provenance.add_record(
            url=self.base_url,
            method="collect",
            confidence=0.85,
            metadata={
                "source": "pbia_cgee",
                "pages_collected": len(results),
                "pages_ok": sum(
                    1
                    for r in results
                    if "erro" not in r["titulo"].lower() and "falha" not in r["titulo"].lower()
                ),
            },
        )

        return results

    async def get_provenance_records(self) -> list[dict[str, Any]]:
        """Retorna os registros de proveniência.

        Returns:
            Lista de registros de proveniência
        """
        records = self.provenance.get_records()
        return [record.model_dump() for record in records]

    async def close(self) -> None:
        """Limpa recursos do fetcher."""
        await self.fetcher.close()
