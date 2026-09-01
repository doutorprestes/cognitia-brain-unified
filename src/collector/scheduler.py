"""IA Brasil — Agendador de coleta de dados.

Este módulo implementa o agendamento e a execução de tarefas de coleta de
dados das diferentes fontes, usando o registry único de fontes (issue #1079).

Cada execução de fonte:
- adquire um lock distribuído (evita coleta duplicada entre workers);
- persiste um ``IngestionRun`` com state machine ``queued/running/success/
  partial/error`` desde o início;
- persiste ``Fonte`` quando os itens coletados trazem ``fonte_url``.

Uso:
    from src.collector.scheduler import CollectorScheduler

    scheduler = CollectorScheduler()
    await scheduler.run_all_sources()
"""

from __future__ import annotations

import asyncio
from datetime import date, datetime, timedelta
from typing import TYPE_CHECKING, Any, cast

from loguru import logger

from src.collector.hashing import stable_hash
from src.collector.locking import source_lock
from src.collector.raw_store import (
    PARSER_VERSION_KEY,
    QUARANTINE_REASON_KEY,
    RAW_CHECKSUM_KEY,
    RAW_KIND_KEY,
    RAW_PATH_KEY,
    RAW_SIZE_KEY,
    save_raw,
)
from src.collector.registry import collector_classes
from src.collector.runs import RunLedger, RunStatus
from src.collector.versioning import persist_item
from src.core.db import IngestionRun, get_session

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

# Versão default do parser quando o coletor não a declara explicitamente.
_DEFAULT_PARSER_VERSION = "1.0.0"


class CollectorScheduler:
    """Agenda e executa a coleta de dados das fontes registradas.

    Attributes:
        sources: Mapeamento chave do coletor → classe do coletor real,
            construído a partir do registry único validado contra sources.yaml.
    """

    def __init__(self) -> None:
        self.sources: dict[str, type] = collector_classes()

    async def run_source(
        self,
        source_name: str,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """Executa a coleta de dados de uma fonte específica.

        Cria um ``IngestionRun`` (queued → running) antes da coleta, adquire o
        lock distribuído da fonte e finaliza o run com status terminal.

        Args:
            source_name: Nome da fonte (chave do coletor).
            **kwargs: Argumentos específicos da fonte.

        Returns:
            Dicionário com resultados, proveniência e status terminal.

        Raises:
            ValueError: Se a fonte não existir.
        """
        if source_name not in self.sources:
            raise ValueError(f"Unknown source: {source_name}")

        ledger = RunLedger(source=source_name)
        await ledger.start()

        async with source_lock(source_name) as acquired:
            if not acquired:
                await ledger.finish(
                    RunStatus.partial,
                    error_message="coleta pulada: outro worker detém o lock da fonte",
                )
                logger.warning(
                    f"[Collector] {source_name} — lock mantido por outro worker; pulando"
                )
                return {
                    "source": source_name,
                    "data": {},
                    "provenance": [],
                    "status": "skipped",
                }

            try:
                collector_class = self.sources[source_name]
                collector = collector_class(**kwargs)
                data = await self._collect_data(source_name, collector)
                provenance = await self._safe_provenance(collector)
                items = _count_items(data)

                # Preserva o payload bruto em disco (imutável) ANTES de decidir
                # o status — inclusive quando o parse é suspeito (zero itens),
                # para inspeção/quarentena posterior (issue #1087).
                try:
                    artifact = save_raw(source_name, ledger.run_id, data)
                except Exception as e:
                    logger.warning(f"[Collector] {source_name} — falha ao preservar raw: {e}")
                    artifact = None

                current_hash = stable_hash(data)
                parser_version = _parser_version(collector)

                if items > 0:
                    await self._persist_fontes(_flatten_items(data))
                    status = RunStatus.success
                    error_message: str | None = None
                else:
                    # Quarantine: parse retornou zero itens (possível mudança de
                    # layout ou página sem métricas) — run termina partial, não error.
                    status = RunStatus.partial
                    error_message = (
                        "parse retornou zero itens com payload preservado "
                        "(possível mudança de layout da fonte)"
                    )

                previous_hash = await self._latest_hash(source_name)
                metadata: dict[str, Any] = {
                    "state": status.value,
                    PARSER_VERSION_KEY: parser_version,
                    "current_hash": current_hash,
                    "previous_hash": previous_hash,
                }
                # Cadência declarada da fonte (issue #1103): periodicidade
                # ("2x/ano" quando o coletor declara PERIODICIDADE, senão
                # "manual") e ultima_referencia (data do documento oficial,
                # extraída pela coleta quando parseável).
                metadata.update(_cadence_metadata(collector))
                if artifact is not None:
                    metadata.update(
                        {
                            RAW_PATH_KEY: artifact.path,
                            RAW_CHECKSUM_KEY: artifact.checksum,
                            RAW_SIZE_KEY: artifact.size,
                            RAW_KIND_KEY: artifact.kind,
                        }
                    )
                if status is RunStatus.partial:
                    metadata[QUARANTINE_REASON_KEY] = error_message

                await ledger.finish(
                    status,
                    items_fetched=items,
                    error_message=error_message,
                    metadata=metadata,
                )
                await self._update_run_hashes(ledger.run_id, previous_hash, current_hash)
                logger.info(
                    f"[Collector] {source_name} concluído: status={status.value}, items={items}"
                )
                return {
                    "source": source_name,
                    "data": data,
                    "provenance": provenance,
                    "status": status.value,
                }
            except Exception as e:
                logger.error(f"Error running source {source_name}: {e}")
                await ledger.finish(RunStatus.error, error_message=str(e))
                return {
                    "source": source_name,
                    "data": {},
                    "provenance": [],
                    "status": "error",
                    "error": str(e),
                }

    async def _collect_data(self, source_name: str, collector: Any) -> dict[str, Any]:
        """Executa os métodos específicos de cada fonte e monta o payload."""
        if source_name == "cgu":
            # Despesas de todos os programas de CT&I (2025 e 2024) + órgãos
            cti_expenses = await collector.fetch_all_cti_expenses(year=2025)
            cti_expenses_2024 = await collector.fetch_all_cti_expenses(year=2024)
            agencies = await collector.list_agencies(system="siafi", page=1)
            return {
                "cti_expenses_2025": cti_expenses,
                "cti_expenses_2024": cti_expenses_2024,
                "agencies": agencies,
            }
        if source_name == "dados_gov_br":
            datasets = await collector.search_datasets("execução orçamentária")
            return {"datasets": datasets}
        if source_name == "dou":
            today = datetime.now()
            yesterday = (today - timedelta(days=1)).strftime("%Y-%m-%d")
            section1 = await collector.scrape_section(1, date=yesterday)
            section2 = await collector.scrape_section(2, date=yesterday)
            return {"section1": section1, "section2": section2}
        if source_name == "mcti":
            news = await collector.fetch_recent_news()
            publications = await collector.fetch_publications()
            return {"news": news, "publications": publications}
        # Genérico: fontes com método collect() unificado (obia, mcti_monitor,
        # pbia_powerbi, pbia_cgee, etc.)
        collect = getattr(collector, "collect", None)
        if collect is not None:
            evidence = await cast("Callable[..., Awaitable[Any]]", collect)()
            return {"evidence": evidence}
        return {}

    async def _safe_provenance(self, collector: Any) -> list[dict[str, Any]]:
        """Obtém registros de proveniência sem propagar falhas."""
        try:
            records = await collector.get_provenance_records()
            return list(records) if isinstance(records, list) else []
        except Exception as e:
            logger.warning(f"[Collector] Falha ao obter provenance: {e}")
            return []

    async def _persist_fontes(self, items: list[Any]) -> None:
        """Upsert de ``Fonte`` + ``Evidencia`` com versionamento (issue #1087).

        Itens coletados com ``fonte_url`` são persistidos via
        ``persist_item`` (fingerprint content-addressed): conteúdo novo gera
        nova versão de evidência, conteúdo igual é ignorado. Falhas de
        persistência são logadas e não propagam, para não alterar o status
        do run.
        """
        seen: set[str] = set()
        to_persist: list[dict[str, Any]] = []
        for item in items:
            if not isinstance(item, dict):
                continue
            url = item.get("fonte_url")
            if isinstance(url, str) and url and url not in seen:
                seen.add(url)
                to_persist.append(item)
        if not to_persist:
            return

        try:
            async with get_session() as session:
                for item in to_persist:
                    url = cast("str", item.get("fonte_url"))
                    titulo = item.get("titulo")
                    await persist_item(
                        session,
                        url=url,
                        titulo=str(titulo)[:512] if titulo else url[:512],
                        content_text=_item_text(item),
                        tipo_evidencia=str(item.get("tipo", "outro")),
                        confianca=_to_float(item.get("confianca")),
                    )
        except Exception as e:
            logger.warning(f"[Collector] Falha ao persistir fontes: {e}")

    @staticmethod
    async def _latest_hash(source_name: str) -> str | None:
        """Hash estável do último run bem-sucedido da fonte (change detection)."""
        from sqlalchemy import select

        async with get_session() as session:
            result = await session.execute(
                select(IngestionRun.current_hash)
                .where(
                    IngestionRun.source == source_name,
                    IngestionRun.status == RunStatus.success.value,
                    IngestionRun.current_hash.is_not(None),
                )
                .order_by(IngestionRun.started_at.desc(), IngestionRun.id.desc())
                .limit(1)
            )
            return result.scalar_one_or_none()

    @staticmethod
    async def _update_run_hashes(
        run_id: str,
        previous_hash: str | None,
        current_hash: str,
    ) -> None:
        """Persiste previous/current hash no run (o ledger não expõe esses campos)."""
        try:
            async with get_session() as session:
                run = await session.get(IngestionRun, run_id)
                if run is None:
                    return
                run.previous_hash = previous_hash
                run.current_hash = current_hash
        except Exception as e:
            logger.warning(f"[Collector] Falha ao persistir hashes do run {run_id}: {e}")

    async def run_all_sources(self) -> list[dict[str, Any]]:
        """Executa a coleta de dados de todas as fontes.

        Returns:
            Lista de resultados de cada fonte.
        """
        tasks = []
        for source_name in self.sources:
            task = asyncio.create_task(self.run_source(source_name))
            tasks.append(task)

        results = await asyncio.gather(*tasks, return_exceptions=True)

        return [
            result
            if isinstance(result, dict)
            else {
                "source": source_name,
                "status": "error",
                "error": str(result),
            }
            for source_name, result in zip(self.sources.keys(), results)
        ]

    async def run_scheduled_collection(self) -> None:
        """Executa a coleta agendada de dados.

        Esta função implementa a lógica de agendamento para coleta
        diária/semanal conforme especificado na issue.
        Integra com o orquestrador de re-ingestão para versionamento.
        """
        from src.collector.reingestion import ReingestionOrchestrator

        logger.info("Starting scheduled data collection")

        orchestrator = ReingestionOrchestrator()

        # Coleta diária do DOU (via re-ingestão versionada)
        logger.info("Running daily DOU collection via re-ingestion")
        dou_report = await orchestrator.run_weekly_reingestion(days=1, sections=[1, 2])
        logger.info(f"DOU collection completed: {dou_report.status}")

        # Coleta semanal (média prioridade) via scheduler
        weekly_sources = ["cgu", "dados_gov_br", "mcti"]
        for source in weekly_sources:
            logger.info(f"Running weekly collection for {source}")
            result = await self.run_source(source)
            logger.info(f"Completed {source}: {result['status']}")

        logger.info("Scheduled data collection completed")


def _count_items(data: dict[str, Any]) -> int:
    """Conta itens coletados em estruturas aninhadas (listas/dicts)."""
    total = 0
    for value in data.values():
        if isinstance(value, (list, dict)):
            total += len(value)
    return total


def _flatten_items(data: dict[str, Any]) -> list[Any]:
    """Achata listas/dicts aninhados em uma lista única de itens."""
    items: list[Any] = []
    for value in data.values():
        if isinstance(value, list):
            items.extend(value)
        elif isinstance(value, dict):
            items.extend(value.values())
    return items


def _parser_version(collector: Any) -> str:
    """Versão do parser/coletor (declarada via ``PARSER_VERSION`` ou default).

    Args:
        collector: Instância do coletor.

    Returns:
        String com a versão do parser.
    """
    version = getattr(collector, "PARSER_VERSION", None)
    if isinstance(version, str) and version:
        return version
    return _DEFAULT_PARSER_VERSION


def _cadence_metadata(collector: Any) -> dict[str, Any]:
    """Extrai a cadência declarada do coletor para persistir no run (issue #1103).

    Lê ``PERIODICIDADE`` (atributo de classe, ex.: ``"2x/ano"``) e
    ``ultima_referencia`` (atributo de instância setado pela coleta, ex.: data
    do relatório oficial). Coletores sem declaração explícita são registrados
    como ``"manual"`` — garantindo que toda fonte tenha a cadência declarada no
    ``IngestionRun.metadata_json``.

    Args:
        collector: Instância do coletor.

    Returns:
        Dict com ``periodicidade`` e, quando disponível, ``ultima_referencia``.
    """
    periodicidade = getattr(collector, "PERIODICIDADE", None)
    if not (isinstance(periodicidade, str) and periodicidade):
        periodicidade = "manual"

    metadata: dict[str, Any] = {"periodicidade": periodicidade}

    ultima_ref = getattr(collector, "ultima_referencia", None)
    # Só aceita tipos serializáveis reais (MagicMock/objetos arbitrários
    # quebram o json.dumps do ledger — issue #1087/#1103).
    if isinstance(ultima_ref, (str, int, float, date, datetime)):
        if isinstance(ultima_ref, (date, datetime)):
            metadata["ultima_referencia"] = ultima_ref.isoformat()
        else:
            metadata["ultima_referencia"] = str(ultima_ref)

    return metadata


def _item_text(item: dict[str, Any]) -> str:
    """Extrai o conteúdo textual do item (base do fingerprint)."""
    for key in ("descricao", "text", "summary", "trecho"):
        value = item.get(key)
        if isinstance(value, str) and value:
            return value
    return ""


def _to_float(value: Any) -> float | None:
    """Converte valor arbitrário em float (tolerante)."""
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value)
        except ValueError:
            return None
    return None
