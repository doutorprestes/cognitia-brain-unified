"""IA Brasil — Coletor para Portal da Transparência (CGU).

Este módulo implementa a coleta de dados da API do Portal da Transparência
da Controladoria-Geral da União (CGU).

Endpoints:
    - /despesas/por-funcional-programatica — Despesas por função/programa/ação
    - /despesas/por-orgao — Despesas por órgão
    - /orgaos-siafi — Órgãos SIAFI
    - /licitacoes — Licitações (requer codigoOrgao)
    - /contratos — Contratos (requer codigoOrgao)

Uso:
    from src.collector.sources.cgu_portal_transparencia import CGUCollector

    collector = CGUCollector(api_key="sua_chave_aqui")
    data = await collector.fetch_expenses_by_program(programa="2021", year=2025)
"""

from __future__ import annotations

import os
from typing import Any

from loguru import logger

from src.collector.core.fetcher import HTTPFetcher
from src.collector.core.provenance import ProvenanceTracker

# Programas SIAFI relacionados a CT&I (Ciência, Tecnologia e Inovação)
CTI_PROGRAMS = {
    "2021": "CIENCIA, TECNOLOGIA E INOVACAO",
    "2308": "CONSOLIDACAO DO SNCTI",
    "2304": "CIENCIA, TECNOLOGIA E INOVACAO PARA O DESENVOLVIMENTO SOCIAL",
    "2208": "TECNOLOGIAS APLICADAS, INOVACAO E DESENVOLVIMENTO SUSTENTAVEL",
    "2106": "PROGRAMA DE GESTAO E MANUTENCAO DO MCTI",
    "1110": "DESENVOLVIMENTO DA NANOCIENCIA E DA NANOTECNOLOGIA",
    "1112": "DIFUSAO E POPULARIZACAO DA CIENCIA",
    "1122": "CIENCIA, TECNOLOGIA E INOVACAO APLICADAS AOS RECURSOS NATURAIS",
    "1201": "CIENCIA, TECNOLOGIA E INOVACAO NO COMPLEXO DA SAUDE",
    "1388": "CIENCIA, TECNOLOGIA E INOVACAO PARA A PITCE",
}


class CGUCollector:
    """Classe para coletar dados do Portal da Transparência (CGU).

    Attributes:
        api_key: Chave de API para autenticação
        base_url: URL base da API
        fetcher: Instância do HTTPFetcher
        provenance: Instância do ProvenanceTracker
    """

    def __init__(self, api_key: str | None = None) -> None:
        self.api_key = api_key or os.getenv("CGU_API_KEY")
        if not self.api_key:
            raise ValueError("CGU_API_KEY not provided and not found in environment")

        self.base_url = "https://api.portaldatransparencia.gov.br/api-de-dados"
        # CGU API é instável com muita frequência — ~1 req/3s é o máximo seguro
        self.fetcher = HTTPFetcher(rate_limit=1, cache_ttl=3600)
        self.parser = None
        self.provenance = ProvenanceTracker()

    async def _fetch_data(
        self,
        endpoint: str,
        params: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        """Busca dados da API do Portal da Transparência.

        A API retorna listas JSON diretamente (array de objetos).
        A resposta é tipada como list[Any] pois o Pydantic converte para list.
        Usamos cast explícito pois o validador do HTTPResponse aceita list.

        NOTA: A CGU API tem comportamento instável — retorna 400 "Erro ao
        executar a consulta" quando chamada em alta frequência.
        Esta função faz retry com backoff para contornar isso.

        Args:
            endpoint: Endpoint da API (ex: "despesas/por-funcional-programatica")
            params: Parâmetros da requisição

        Returns:
            Lista de registros

        Raises:
            ValueError: Se a chave de API não estiver configurada
        """
        if not self.api_key:
            raise ValueError("CGU_API_KEY not configured")

        url = f"{self.base_url}/{endpoint}"
        headers = {
            "chave-api-dados": self.api_key,
            "Accept": "application/json",
        }

        import asyncio as _asyncio

        max_retries = 4
        for attempt in range(max_retries):
            async with self.fetcher as fetcher:
                response = await fetcher.fetch(url, params=params, headers=headers)

                # CGU API sometimes returns 400 "Erro ao executar a consulta"
                # when called too frequently (transient, not a real error)
                if response.status == 429:
                    retry_after = int(response.headers.get("Retry-After", 5))
                    logger.warning(
                        f"CGU API 429 rate limit for {endpoint}. "
                        f"Retry after {retry_after}s (attempt {attempt + 1}/{max_retries})"
                    )
                    await _asyncio.sleep(retry_after)
                    continue

                if response.status == 403:
                    logger.error(f"CGU API 403 Forbidden for {endpoint}")
                    raise ValueError(
                        f"CGU API access denied (403) for {endpoint}. "
                        "A chave pode não ter acesso a este endpoint."
                    )

                if response.status != 200:
                    msg = str(response.data)[:200] if response.data else ""
                    if attempt < max_retries - 1:
                        logger.warning(
                            f"CGU API {response.status} for {endpoint} "
                            f"(attempt {attempt + 1}/{max_retries}): {msg}"
                        )
                        # Backoff exponencial: 3, 6, 12s
                        await _asyncio.sleep(3 * (2**attempt))
                        continue
                    logger.error(f"CGU API {response.status} for {endpoint}: {msg}")
                    raise ValueError(f"CGU API returned status {response.status} for {endpoint}")

            self.provenance.add_record(
                url=url,
                method="GET",
                confidence=0.9,
                metadata={"endpoint": endpoint, "params": params},
            )

            data = response.data
            if isinstance(data, list):
                return data
            if isinstance(data, dict):
                if "Erro na API" in data:
                    logger.warning(f"CGU API error for {endpoint}: {data['Erro na API']}")
                    return []
                msg = f"CGU API returned dict instead of list for {endpoint}: {data}"
                raise ValueError(msg)

            return []

        raise ValueError(f"CGU API failed after {max_retries} attempts for {endpoint}")

    async def fetch_expenses_by_program(
        self,
        programa: str,
        year: int = 2025,
        page: int = 1,
    ) -> list[dict[str, Any]]:
        """Busca despesas por programa (classificação funcional-programática).

        Endpoint: /despesas/por-funcional-programatica

        Args:
            programa: Código SIAFI do programa (ex: "2021" para CT&I)
            year: Ano das despesas
            page: Número da página

        Returns:
            Lista de despesas com campos: funcao, subfuncao, programa,
            acao, codigoAcao, empenhado, liquidado, pago
        """
        params: dict[str, Any] = {
            "ano": year,
            "programa": programa,
            "pagina": page,
        }

        return await self._fetch_data("despesas/por-funcional-programatica", params)

    async def fetch_all_cti_expenses(
        self,
        year: int = 2025,
    ) -> dict[str, list[dict[str, Any]]]:
        """Busca despesas de todos os programas de CT&I.

        Args:
            year: Ano das despesas

        Returns:
            Dicionário com código do programa como chave e lista de despesas como valor
        """
        results: dict[str, list[dict[str, Any]]] = {}
        for prog in CTI_PROGRAMS:
            page = 1
            all_records: list[dict[str, Any]] = []
            while True:
                try:
                    records = await self.fetch_expenses_by_program(
                        programa=prog, year=year, page=page
                    )
                    if not records:
                        break
                    all_records.extend(records)
                    if len(records) < 15:  # menos que o page size = última página
                        break
                    page += 1
                except ValueError as e:
                    logger.warning(f"Error fetching programa {prog}: {e}")
                    break
            if all_records:
                results[prog] = all_records
                logger.info(
                    f"Programa {prog} ({CTI_PROGRAMS[prog][:40]}): {len(all_records)} registros"
                )
        return results

    async def fetch_expenses_by_agency(
        self,
        year: int = 2025,
        orgao_superior: str | None = "24000",  # MCTI
        page: int = 1,
    ) -> list[dict[str, Any]]:
        """Busca despesas por órgão.

        Endpoint: /despesas/por-orgao

        Args:
            year: Ano das despesas
            orgao_superior: Código SIAFI do órgão superior (default: 24000 = MCTI)
            page: Número da página

        Returns:
            Lista de despesas por órgão
        """
        params: dict[str, Any] = {
            "ano": year,
            "pagina": page,
        }
        if orgao_superior:
            params["orgaoSuperior"] = orgao_superior

        return await self._fetch_data("despesas/por-orgao", params)

    async def list_agencies(
        self,
        system: str = "siafi",
        page: int = 1,
    ) -> list[dict[str, Any]]:
        """Lista órgãos cadastrados.

        Args:
            system: "siafi" ou "siape"
            page: Número da página

        Returns:
            Lista de órgãos
        """
        endpoint = f"orgaos-{system}"
        params = {"pagina": page}
        return await self._fetch_data(endpoint, params)

    async def get_provenance_records(self) -> list[dict[str, Any]]:
        """Retorna os registros de proveniência.

        Returns:
            Lista de registros de proveniência
        """
        records = self.provenance.get_records()
        return [record.model_dump() for record in records]
