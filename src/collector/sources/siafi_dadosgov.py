"""Coletor de dados do SIAFI via dados.gov.br (CKAN).

Busca dados abertos de execução orçamentária do Tesouro Nacional
publicados no portal dados.gov.br.
"""

from __future__ import annotations

import csv
import io
from typing import Any

from src.collector.core.fetcher import HTTPFetcher
from src.collector.core.provenance import ProvenanceTracker


class SIAFICollector:
    """Coleta dados de execução orçamentária do SIAFI via dados.gov.br."""

    BASE_URL = "https://dados.gov.br/api/3/action"
    SEARCH_TERMS = [
        "execucao orcamentaria uniao",
        "despesa publica federal",
        "siafi execucao",
    ]

    def __init__(self) -> None:
        self.fetcher = HTTPFetcher(rate_limit=1, cache_ttl=3600)
        self.provenance = ProvenanceTracker()

    async def _search_datasets(self, query: str) -> list[dict[str, Any]]:
        """Busca datasets no CKAN por termo de pesquisa."""
        url = f"{self.BASE_URL}/package_search"
        params = {"q": query, "rows": 5}
        async with self.fetcher:
            resp = await self.fetcher.fetch(url, params=params)
            if resp and resp.status == 200 and isinstance(resp.data, dict):
                result = resp.data.get("result", {})
                if isinstance(result, dict):
                    results = result.get("results", [])
                    if isinstance(results, list):
                        return results
        return []

    async def _get_resource_data(self, resource_url: str) -> list[dict[str, Any]]:
        """Baixa e parseia um recurso CSV do CKAN."""
        async with self.fetcher:
            resp = await self.fetcher.fetch(resource_url)
            if not resp or resp.status != 200:
                return []
            content = resp.data if isinstance(resp.data, str) else ""
            if not content:
                return []
            reader = csv.DictReader(io.StringIO(content))
            return list(reader)

    async def collect(self) -> list[dict[str, Any]]:
        """Coleta dados de execução orçamentária.

        Returns:
            Lista de dicts no formato padronizado de evidência.
        """
        evidence_items: list[dict[str, Any]] = []

        for term in self.SEARCH_TERMS:
            try:
                datasets = await self._search_datasets(term)
                for ds in datasets:
                    resources = ds.get("resources", [])
                    for res in resources:
                        if res.get("format", "").upper() == "CSV":
                            url = res.get("url", "")
                            if url:
                                rows = await self._get_resource_data(url)
                                for row in rows[:50]:
                                    title = (
                                        row.get("Nome_Programa", "")
                                        or row.get("programa", "")
                                        or term
                                    )
                                    desc = str(row)[:500]
                                    evidence_items.append(
                                        {
                                            "titulo": f"SIAFI: {title}",
                                            "descricao": desc,
                                            "data": row.get(
                                                "Data_Inscricao_NOB",
                                                row.get("exercicio", ""),
                                            ),
                                            "fonte_url": url,
                                            "tipo": "ato_oficial",
                                        }
                                    )
                                    self.provenance.add_record(
                                        url=url,
                                        method="CKAN API",
                                        confidence=0.8,
                                    )
            except Exception:
                continue

        return evidence_items

    async def get_provenance_records(self) -> list[dict[str, Any]]:
        """Retorna registros de proveniência da coleta."""
        records = self.provenance.get_records()
        return [record.model_dump() for record in records]
