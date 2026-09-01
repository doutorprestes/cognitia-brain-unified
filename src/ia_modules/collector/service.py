"""Serviço de coleta de dados — IA Brasil.

Provedor de operações para coleta automática de dados do PBIA e fontes oficiais.
Segue as regras de negócio do collector-pbia-design.md (Approach C).
"""

import asyncio
from abc import ABC, abstractmethod
from collections.abc import Iterator
from concurrent.futures import ProcessPoolExecutor
from datetime import datetime
from typing import Any
from uuid import uuid4

from loguru import logger
from pydantic import HttpUrl

from src.modules.collector.schemas import (
    CollectorConfig,
    CollectorResult,
    CollectorType,
    FieldProvenance,
    SourceMetadata,
)

# ---------------------------------------------------------------------------
# Core Protocols (Approach C)
# ---------------------------------------------------------------------------


class Collector(ABC):
    """Protocolo base para todos os coletores."""

    name: CollectorType
    source_url: HttpUrl
    schedule: str

    @abstractmethod
    def fetch(self) -> Iterator[bytes]:
        """Busca dados da fonte e retorna bytes brutos."""
        pass

    @abstractmethod
    def parse(self, raw: bytes) -> list[dict[str, Any]]:
        """Parseia bytes brutos para dados estruturados."""
        pass

    @abstractmethod
    def extract(self, parsed: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Extrai informações adicionais usando LLM (opcional)."""
        pass

    def collect(self) -> CollectorResult:
        """Executa o pipeline completo: fetch → parse → extract."""
        logger.info(f"Iniciando coleta para {self.name.value}")

        # Fetch
        raw_data = list(self.fetch())
        if not raw_data:
            logger.warning(f"Nenhum dado obtido para {self.name.value}")
            return CollectorResult(
                items=[],
                provenance={},
                source_metadata=SourceMetadata(
                    source_url=self.source_url,
                    fetch_timestamp=datetime.now(),
                ),
            )

        # Parse
        parsed_data = []
        for raw_chunk in raw_data:
            parsed_data.extend(self.parse(raw_chunk))

        extracted_data = self.extract(parsed_data)

        # Create provenance
        provenance = self._create_provenance(extracted_data)

        # Create source metadata
        source_metadata = SourceMetadata(
            source_url=self.source_url,
            fetch_timestamp=datetime.now(),
        )

        return CollectorResult(
            items=extracted_data,
            provenance=provenance,
            source_metadata=source_metadata,
        )

    def _create_provenance(self, items: list[dict[str, Any]]) -> dict[str, FieldProvenance]:
        """Cria provenance para cada item."""
        provenance = {}
        for i, item in enumerate(items):
            item_id = item.get("id", str(uuid4()))
            provenance[item_id] = FieldProvenance(
                source_url=self.source_url,
                method="pdf_text",  # Default, será sobrescrito pelos coletores específicos
                timestamp=datetime.now(),
                confidence=0.8,  # Default confidence
                raw_ref=f"item_{i}",
                parser_version="1.0.0",
            )
        return provenance


# ---------------------------------------------------------------------------
# Collector Service
# ---------------------------------------------------------------------------


class CollectorService:
    """Serviço principal para gerenciamento de coletores."""

    def __init__(self) -> None:
        self.collectors: dict[CollectorType, Collector] = {}

    def register_collector(self, collector: Collector) -> None:
        """Registra um coletor."""
        self.collectors[collector.name] = collector
        logger.info(f"Coletor registrado: {collector.name.value}")

    def get_collector(self, name: CollectorType) -> Collector | None:
        """Obtém um coletor pelo nome."""
        return self.collectors.get(name)

    async def collect(self, name: CollectorType, parallel: bool = False) -> CollectorResult:
        """Executa coleta para um coletor específico."""
        collector = self.get_collector(name)
        if not collector:
            raise ValueError(f"Coletor não encontrado: {name.value}")

        if parallel:
            # Executa em processo separado para isolamento sem bloquear o event loop
            with ProcessPoolExecutor(max_workers=1) as executor:
                future = executor.submit(collector.collect)
                return await asyncio.wrap_future(future)
        else:
            # Executa em thread do event loop para não bloquear a execução async
            return await asyncio.to_thread(collector.collect)

    async def collect_all(self, parallel: bool = True) -> dict[str, CollectorResult]:
        """Executa coleta para todos os coletores."""
        results = {}

        if parallel:
            # Executa em paralelo usando ProcessPoolExecutor sem bloquear o event loop
            with ProcessPoolExecutor(max_workers=len(self.collectors)) as executor:
                futures = {
                    name: executor.submit(collector.collect)
                    for name, collector in self.collectors.items()
                }

                for name, future in futures.items():
                    try:
                        results[name.value] = await asyncio.wrap_future(future)
                        logger.info(f"Coleta concluída para {name.value}")
                    except Exception as e:
                        logger.error(f"Erro na coleta {name.value}: {e}")
                        collector = self.collectors[name]
                        results[name.value] = CollectorResult(
                            items=[],
                            provenance={},
                            source_metadata=SourceMetadata(
                                source_url=collector.source_url,
                                fetch_timestamp=datetime.now(),
                            ),
                        )
        else:
            # Executa sequencialmente em threads para não bloquear o event loop
            for name, collector in self.collectors.items():
                try:
                    results[name.value] = await asyncio.to_thread(collector.collect)
                    logger.info(f"Coleta concluída para {name.value}")
                except Exception as e:
                    logger.error(f"Erro na coleta {name.value}: {e}")
                    results[name.value] = CollectorResult(
                        items=[],
                        provenance={},
                        source_metadata=SourceMetadata(
                            source_url=collector.source_url,
                            fetch_timestamp=datetime.now(),
                        ),
                    )

        return results


# ---------------------------------------------------------------------------
# Source Adapters (Initial Implementations)
# ---------------------------------------------------------------------------


class MCTIPlanCollector(Collector):
    """Coletor para o PDF do plano PBIA (MCTI).

    ATENÇÃO: Implementação placeholder — fetch e parse ainda não
    foram implementados. O endpoint de status reporta status degradado.
    """

    _is_stub: bool = True

    def __init__(self, config: CollectorConfig):
        self.name = CollectorType.MCTI_PLAN
        self.source_url = config.source_url
        self.schedule = config.schedule

    def fetch(self) -> Iterator[bytes]:
        """Busca o PDF do plano PBIA."""
        # TODO: Implementar fetch real com HTTP client
        logger.info(f"Fetching PDF from {self.source_url}")
        # Simulação: retorna bytes vazios para agora
        yield b""  # Placeholder

    def parse(self, raw: bytes) -> list[dict[str, Any]]:
        """Parseia PDF para extrair eixos e metas."""
        # TODO: Implementar parsing real com pdfplumber
        logger.info("Parsing PDF do plano PBIA")
        _ = raw  # Unused parameter (TODO: implement real parsing)
        # Simulação: retorna estrutura básica
        return [
            {
                "id": "eixo_1",
                "titulo": "Eixo 1 - Pesquisa e Desenvolvimento",
                "descricao": "Promover pesquisa em IA",
                "ordem": 1,
            }
        ]

    def extract(self, parsed: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Extrai informações adicionais usando LLM."""
        # TODO: Implementar extração com LLM (Mistral Vibe CLI)
        logger.info("Extraindo informações com LLM")
        return parsed


class CGUTransparenciaCollector(Collector):
    """Coletor para o Portal da Transparência (CGU).

    ATENÇÃO: Implementação placeholder — fetch e parse ainda não
    foram implementados. O endpoint de status reporta status degradado.
    """

    _is_stub: bool = True

    def __init__(self, config: CollectorConfig):
        self.name = CollectorType.CGU_TRANSPARENCIA
        self.source_url = config.source_url
        self.schedule = config.schedule

    def fetch(self) -> Iterator[bytes]:
        """Busca dados do Portal da Transparência."""
        # TODO: Implementar fetch real com API REST
        logger.info(f"Fetching data from {self.source_url}")
        yield b""  # Placeholder

    def parse(self, raw: bytes) -> list[dict[str, Any]]:
        """Parseia JSON/CSV para extrair projetos de execução."""
        # TODO: Implementar parsing real
        logger.info("Parsing dados do Portal da Transparência")
        _ = raw  # Unused parameter (TODO: implement real parsing)
        return []

    def extract(self, parsed: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Extrai informações adicionais usando LLM."""
        # TODO: Implementar extração com LLM
        return parsed


# ---------------------------------------------------------------------------
# Factory Functions
# ---------------------------------------------------------------------------


def create_collector_service() -> CollectorService:
    """Cria e configura o serviço de coleta com coletores padrão."""
    service = CollectorService()

    # Registrar coletores padrão
    mcti_config = CollectorConfig(
        name=CollectorType.MCTI_PLAN,
        source_url="https://www.gov.br/mcti/pt-br/acompanhe-o-mcti/ia-brasil/plano-brasileiro-de-inteligencia-artificial-pbia",
        schedule="0 6 * * 1",  # Segundas-feiras às 6h
    )
    service.register_collector(MCTIPlanCollector(mcti_config))

    cgu_config = CollectorConfig(
        name=CollectorType.CGU_TRANSPARENCIA,
        source_url="https://portaldatransparencia.gov.br/api-de-dados",
        schedule="0 3 * * *",  # Diariamente às 3h
    )
    service.register_collector(CGUTransparenciaCollector(cgu_config))

    return service
