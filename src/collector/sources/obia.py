"""IA Brasil — Coletor para o Observatório Brasileiro de IA (OBIA).

Coleta dados do OBIA (obia.nic.br), indicadores de adoção de IA,
produção científica, centros de IA e cursos superiores em IA.

Fonte: Ação 52 do PBIA — Observatório Brasileiro de IA
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from loguru import logger

from src.collector.core.fetcher import HTTPFetcher
from src.collector.core.provenance import ProvenanceTracker

# AVISO: a extração automática de indicadores do OBIA ainda não foi
# implementada. Os itens retornados são descrições estáticas cadastradas
# manualmente e NÃO refletem indicadores extraídos da página na coleta.
# Usado em ``metadata["aviso"]`` e ``metadata["dados_estaticos"]`` para
# evitar que dados descritivos sejam tratados como extração real.
_STATIC_DATA_NOTE = (
    "Dados estáticos: descrição cadastrada manualmente. A extração automática "
    "de indicadores do OBIA ainda não é realizada por este coletor."
)


class OBIACollector:
    """Coletor para o Observatório Brasileiro de IA."""

    BASE_URL = "https://obia.nic.br"
    # Versão do parser/coletor (registrada no IngestionRun — issue #1087).
    PARSER_VERSION = "1.1.0"
    PAGES = {
        "indicadores": "/s/indicadores",
        "centros": "/s/centros",
        "cursos": "/mapeamento-dos-cursos-superiores-em-inteligencia-artificial-no-brasil",
    }

    def __init__(self) -> None:
        self._fetcher: HTTPFetcher | None = None
        self.provenance = ProvenanceTracker()

    async def _ensure_fetcher(self) -> HTTPFetcher:
        if self._fetcher is None:
            self._fetcher = HTTPFetcher()
            await self._fetcher.initialize()
        return self._fetcher

    async def collect(self) -> list[dict[str, Any]]:
        fetcher = await self._ensure_fetcher()
        evidence_items: list[dict[str, Any]] = []

        try:
            for key, path in self.PAGES.items():
                url = f"{self.BASE_URL}{path}"
                try:
                    result = await fetcher.fetch(url)
                    if result and result.data:
                        html = result.data if isinstance(result.data, str) else str(result.data)
                        items = self._parse_page(html, url, key)
                        evidence_items.extend(items)
                        self.provenance.add_record(
                            url=url,
                            method="GET",
                            confidence=0.6,
                            metadata={
                                "source": "obia",
                                "page": key,
                                "dados_estaticos": True,
                            },
                        )
                        logger.info(f"OBIA {key}: {len(items)} items from {url}")
                except Exception as e:
                    logger.warning(f"OBIA {key} failed for {url}: {e}")
        finally:
            await self.close()

        return evidence_items

    def _parse_page(self, _html: str, url: str, page_type: str) -> list[dict[str, Any]]:
        items: list[dict[str, Any]] = []
        now = datetime.now(UTC).isoformat()

        if page_type == "indicadores":
            items.append(
                {
                    "titulo": "OBIA — Indicadores de IA no Brasil",
                    "descricao": (
                        "Indicadores de adoção de IA por setores (educação, empresas, "
                        "governo, saúde), produção de conhecimento e formação. "
                        "Disponível em obia.nic.br/s/indicadores"
                    ),
                    "data": now,
                    "fonte_url": url,
                    "tipo": "relatorio",
                    "confianca": 0.85,
                    "metadata": {
                        "fonte": "OBIA/NIC.br",
                        "tipo": "indicadores_macro",
                        "dados_estaticos": True,
                        "aviso": _STATIC_DATA_NOTE,
                    },
                }
            )

        elif page_type == "centros":
            items.append(
                {
                    "titulo": "OBIA — Centros de IA no Brasil",
                    "descricao": (
                        "Rede de centros de IA públicos e privados em operação no Brasil. "
                        "Inclui C4AI/USP, CIn-UFPE, Coppe/UFRJ, USP, UNICAMP, UFMG, "
                        "SENAI CIMATEC, UFC, IPT, entre outros."
                    ),
                    "data": now,
                    "fonte_url": url,
                    "tipo": "relatorio",
                    "confianca": 0.85,
                    "metadata": {
                        "fonte": "OBIA/NIC.br",
                        "tipo": "centros_ia",
                        "dados_estaticos": True,
                        "aviso": _STATIC_DATA_NOTE,
                    },
                }
            )

        elif page_type == "cursos":
            items.append(
                {
                    "titulo": "OBIA — Mapeamento de Cursos Superiores em IA",
                    "descricao": (
                        "Mapeamento dos cursos superiores em inteligência artificial "
                        "no Brasil, incluindo graduação e pós-graduação."
                    ),
                    "data": now,
                    "fonte_url": url,
                    "tipo": "relatorio",
                    "confianca": 0.85,
                    "metadata": {
                        "fonte": "OBIA/NIC.br",
                        "tipo": "cursos_ia",
                        "dados_estaticos": True,
                        "aviso": _STATIC_DATA_NOTE,
                    },
                }
            )

        return items

    async def get_provenance_records(self) -> list[dict[str, Any]]:
        """Retorna os registros de proveniência.

        Returns:
            Lista de registros de proveniência
        """
        records = self.provenance.get_records()
        return [record.model_dump() for record in records]

    async def close(self) -> None:
        if self._fetcher:
            await self._fetcher.close()
            self._fetcher = None
