"""IA Brasil — Coletor para Dados Abertos (dados.gov.br).

Este módulo implementa a coleta de dados da API CKAN do dados.gov.br.

Uso:
    from src.collector.sources.dados_gov_br import DadosGovBRCollector

    collector = DadosGovBRCollector()
    datasets = await collector.search_datasets("execução orçamentária")
"""

from __future__ import annotations

import os
from datetime import UTC, datetime
from typing import Any

from loguru import logger

from src.collector.core.fetcher import HTTPFetcher
from src.collector.core.parser.api_parser import APIParser
from src.collector.core.provenance import ProvenanceTracker


class DadosGovBRCollector:
    """Classe para coletar dados do dados.gov.br.

    A API CKAN do dados.gov.br atualmente requer autenticação.
    Configure a variável de ambiente DADOS_GOV_API_KEY ou passe
    o parâmetro ``api_key`` no construtor.

    Para obter uma chave: https://dados.gov.br/solicitar-api-key
    (ou equivalente no portal de dados abertos atual)

    Attributes:
        api_key: Chave de API opcional para o CKAN
        base_url: URL base da API CKAN
        fetcher: Instância do HTTPFetcher
        parser: Instância do APIParser
        provenance: Instância do ProvenanceTracker
    """

    def __init__(self, api_key: str | None = None) -> None:
        self.api_key = api_key or os.getenv("DADOS_GOV_API_KEY")
        self.base_url = "https://dados.gov.br/api/3"
        self.fetcher = HTTPFetcher(rate_limit=10, cache_ttl=3600)
        self.parser = APIParser()
        self.provenance = ProvenanceTracker()

    async def _fetch_data(
        self,
        endpoint: str,
        params: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Busca dados da API CKAN.

        Args:
            endpoint: Endpoint da API
            params: Parâmetros da requisição

        Returns:
            Dados da resposta

        Raises:
            ValueError: Se a API retornar erro (incluindo 401 não-autorizado)
        """
        url = f"{self.base_url}/{endpoint}"
        headers: dict[str, str] = {}
        if self.api_key:
            headers["Authorization"] = self.api_key

        async with self.fetcher as fetcher:
            response = await fetcher.fetch(url, params=params, headers=headers)

            if response.status == 401:
                msg = (
                    "dados.gov.br API retornou 401 (não autorizado). "
                    "A API CKAN do dados.gov.br agora requer autenticação. "
                    "Configure DADOS_GOV_API_KEY via env ou parâmetro api_key."
                )
                logger.error(msg)
                raise ValueError(msg)

            if response.status != 200:
                logger.error(f"Error fetching data from dados.gov.br API: {response.status}")
                raise ValueError(f"dados.gov.br API returned status {response.status}")

            self.provenance.add_record(
                url=url,
                method="GET",
                confidence=0.85,
                metadata={"endpoint": endpoint, "params": params},
            )

            return response.data if isinstance(response.data, dict) else {}

    async def search_datasets(
        self,
        query: str,
        limit: int = 10,
        rows: int | None = None,
        start: int = 0,
    ) -> list[dict[str, Any]]:
        """Busca datasets no dados.gov.br.

        Aceita tanto ``limit`` quanto ``rows`` para compatibilidade.
        ``limit`` tem precedência sobre ``rows`` quando ambos são fornecidos.

        Args:
            query: Termo de busca
            limit: Número máximo de resultados (padrão: 10). Substitui ``rows``.
            rows: Número de resultados por página (mantido para compatibilidade).
            start: Índice inicial

        Returns:
            Lista de datasets
        """
        # limit tem precedência sobre rows
        effective_rows = limit if rows is None else min(limit, rows)

        params: dict[str, Any] = {
            "q": query,
            "rows": effective_rows,
            "start": start,
        }

        data = await self._fetch_data("action/package_search", params)

        if isinstance(data, dict) and "result" in data and "results" in data["result"]:
            result = data["result"]
            if isinstance(result, dict):
                results = result.get("results", [])
                if isinstance(results, list):
                    return results[:limit]

        return []

    async def get_dataset(
        self,
        dataset_id: str,
    ) -> dict[str, Any]:
        """Obtém informações de um dataset específico.

        Args:
            dataset_id: ID do dataset

        Returns:
            Informações do dataset
        """
        params: dict[str, Any] = {
            "id": dataset_id,
        }

        data = await self._fetch_data("action/package_show", params)

        if isinstance(data, dict) and "result" in data:
            result = data["result"]
            if isinstance(result, dict):
                return result

        return {}

    async def get_dataset_resources(
        self,
        dataset_id: str,
    ) -> list[dict[str, Any]]:
        """Obtém recursos de um dataset.

        Args:
            dataset_id: ID do dataset

        Returns:
            Lista de recursos
        """
        dataset = await self.get_dataset(dataset_id)

        resources = dataset.get("resources")
        if isinstance(resources, list):
            return resources

        return []

    async def collect(self) -> list[dict[str, Any]]:
        """Método unificado de coleta.

        Busca datasets relacionados a IA e PBIA no dados.gov.br
        e retorna uma lista de evidências com campos padronizados.

        Se a API requerer autenticação e nenhuma chave estiver
        configurada, retorna lista vazia com log de aviso.

        Returns:
            Lista de evidências com titulo, descricao, data, fonte_url e tipo
        """
        if not self.api_key:
            logger.warning(
                "DADOS_GOV_API_KEY não configurada. "
                "A API CKAN do dados.gov.br requer autenticação. "
                "Coleta de dados.gov.br será ignorada."
            )
            self.provenance.add_record(
                url=f"{self.base_url}/action/package_search",
                method="collect",
                confidence=0.0,
                metadata={
                    "source": "dados_gov_br",
                    "status": "skipped_no_api_key",
                    "items_count": 0,
                },
            )
            return []

        queries = [
            "inteligência artificial",
            "PBIA",
            "ciência tecnologia",
            "dados abertos",
        ]

        all_items: list[dict[str, Any]] = []
        seen_ids: set[str] = set()

        for query in queries:
            try:
                datasets = await self.search_datasets(query, limit=5)
                for ds in datasets:
                    ds_id = ds.get("id", ds.get("name", ""))
                    if ds_id in seen_ids:
                        continue
                    seen_ids.add(ds_id)

                    titulo = ds.get("title", ds.get("name", "Dataset sem título"))
                    descricao = ds.get("notes", ds.get("description", ""))
                    raw_data = ds.get("metadata_created", ds.get("metadata_modified", ""))
                    if isinstance(raw_data, datetime):
                        raw_data = raw_data.isoformat()
                    fonte_url = ds.get(
                        "url",
                        f"https://dados.gov.br/dataset/{ds.get('name', ds_id)}",
                    )

                    all_items.append(
                        {
                            "titulo": titulo,
                            "descricao": descricao,
                            "data": str(raw_data) if raw_data else datetime.now(UTC).isoformat(),
                            "fonte_url": fonte_url,
                            "tipo": "dataset",
                        }
                    )
            except Exception as e:
                logger.warning(f"Error searching datasets for '{query}': {e}")

        self.provenance.add_record(
            url=f"{self.base_url}/action/package_search",
            method="collect",
            confidence=0.85,
            metadata={
                "source": "dados_gov_br",
                "items_count": len(all_items),
                "queries": queries,
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
