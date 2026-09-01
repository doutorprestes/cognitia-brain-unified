"""Coletor de relatórios MCTI/CGEE para indicadores físicos do PBIA.

Extrai indicadores de resultados de PDFs de prestação de contas
do MCTI e CGEE.
"""

from __future__ import annotations

import re
from typing import Any

from src.collector.core.fetcher import HTTPFetcher
from src.collector.core.provenance import ProvenanceTracker


class MCTIRelatoriosCollector:
    """Coleta indicadores físicos de relatórios MCTI/CGEE."""

    BASE_URLS = [
        "https://www.gov.br/mcti/pt-br/acompanhe-o-mcti",
        "https://cgee.org.br/publicacoes",
    ]

    INDICATOR_PATTERNS = [
        re.compile(
            r"(\d[\d.]*)\s*(pessoas?|profissionais?|indivíduos?)\s*"
            r"(capacitad[ao]s?|treinad[ao]s?|formad[ao]s?)",
            re.IGNORECASE,
        ),
        re.compile(
            r"(\d[\d.]*)\s*(equipamentos?|laborat[oó]rios?|centros?)\s*"
            r"(instalad[ao]s?|implementad[ao]s?|criad[ao]s?)",
            re.IGNORECASE,
        ),
        re.compile(
            r"(\d[\d.]*)\s*(patentes?|projetos?|bolsas?)\s*"
            r"(depositad[ao]s?|aprovad[ao]s?|concedid[ao]s?)",
            re.IGNORECASE,
        ),
    ]

    def __init__(self) -> None:
        self.fetcher = HTTPFetcher(rate_limit=1, cache_ttl=86400)
        self.provenance = ProvenanceTracker()

    def _extract_indicators(self, text: str) -> list[dict[str, str]]:
        """Extrai indicadores físicos do texto usando regex."""
        indicators = []
        for pattern in self.INDICATOR_PATTERNS:
            for match in pattern.finditer(text):
                value = match.group(1).replace(".", "")
                unit = match.group(2)
                action = match.group(3)
                indicators.append(
                    {
                        "valor": value,
                        "unidade": unit,
                        "acao": action,
                        "texto_completo": match.group(0),
                    }
                )
        return indicators

    async def _fetch_page(self, url: str) -> str:
        """Busca conteúdo de texto de uma URL."""
        try:
            async with self.fetcher:
                resp = await self.fetcher.fetch(url)
                if resp and resp.status == 200 and resp.data:
                    return str(resp.data)
        except Exception:
            pass
        return ""

    async def collect(self) -> list[dict[str, Any]]:
        """Coleta indicadores de relatórios MCTI/CGEE.

        Returns:
            Lista de dicts no formato padronizado de evidência.
        """
        evidence_items: list[dict[str, Any]] = []

        for base_url in self.BASE_URLS:
            try:
                text = await self._fetch_page(base_url)
                if not text:
                    continue

                indicators = self._extract_indicators(text)
                for ind in indicators:
                    evidence_items.append(
                        {
                            "titulo": (f"MCTI/CGEE: {ind['valor']} {ind['unidade']} {ind['acao']}"),
                            "descricao": ind["texto_completo"],
                            "data": "",
                            "fonte_url": base_url,
                            "tipo": "relatorio",
                        }
                    )
                    self.provenance.add_record(
                        url=base_url,
                        method="HTML scraping",
                        confidence=0.6,
                    )
            except Exception:
                continue

        return evidence_items

    async def get_provenance_records(self) -> list[dict[str, Any]]:
        """Retorna registros de proveniência."""
        records = self.provenance.get_records()
        return [record.model_dump() for record in records]
