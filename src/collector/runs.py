"""IA Brasil — Run ledger: ciclo de vida de execução de coleta.

State machine persistida de cada execução automática de fonte:

    queued → running → success | partial | error

O run é criado no banco ANTES da coleta (status ``queued``/``running``) e
finalizado com um status terminal ao término, garantindo que toda execução
automática tenha registro rastreável (issue #1079).

Reutiliza o padrão de persistência de ``src/collector/reingestion.py``
(mark_success antes de persistir; falhas de persistência são logadas e não
propagam).

Uso:
    from src.collector.runs import RunLedger, RunStatus

    ledger = RunLedger(source="dou")
    await ledger.start()
    ...
    await ledger.finish(RunStatus.success, items_fetched=10)
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from loguru import logger

from src.core.db import IngestionRun, get_session


class RunStatus(StrEnum):
    """Status possíveis do ciclo de vida de um run de coleta."""

    queued = "queued"
    running = "running"
    success = "success"
    partial = "partial"
    error = "error"


class RunLedger:
    """Persiste o ciclo de vida de uma execução de coleta no IngestionRun.

    Attributes:
        source: Nome da fonte coletada.
        run_id: ID único do run (persistido como PK do IngestionRun).
        started_at: Timestamp de início da execução.
    """

    def __init__(self, source: str) -> None:
        self.source = source
        self.run_id = str(uuid.uuid4())
        self.started_at = datetime.now(UTC)

    async def start(self) -> str:
        """Registra o run com status ``queued`` → ``running`` antes da coleta.

        Returns:
            ID do run criado.
        """
        try:
            async with get_session() as session:
                run = IngestionRun(
                    id=self.run_id,
                    started_at=self.started_at,
                    source=self.source,
                    status=RunStatus.queued.value,
                    metadata_json={"state": RunStatus.queued.value},
                )
                session.add(run)
                await session.flush()
                run.status = RunStatus.running.value
                run.metadata_json = {"state": RunStatus.running.value}
        except Exception as e:
            logger.error(f"[RunLedger] Falha ao iniciar run {self.run_id} ({self.source}): {e}")
        return self.run_id

    async def finish(
        self,
        status: RunStatus,
        *,
        items_fetched: int = 0,
        error_message: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        """Marca um status terminal (``success``/``partial``/``error``).

        Args:
            status: Status terminal do run.
            items_fetched: Total de itens coletados.
            error_message: Mensagem de erro/motivo (para ``error``/``partial``).
            metadata: Metadados adicionais persistidos em ``metadata_json``.
        """
        try:
            async with get_session() as session:
                run = await session.get(IngestionRun, self.run_id)
                if run is None:
                    logger.warning(
                        f"[RunLedger] Run {self.run_id} ({self.source}) não encontrado "
                        "para finalizar"
                    )
                    return
                run.status = status.value
                run.finished_at = datetime.now(UTC)
                run.items_fetched = items_fetched
                run.error_message = error_message
                if metadata:
                    run.metadata_json = metadata
        except Exception as e:
            logger.error(f"[RunLedger] Falha ao finalizar run {self.run_id}: {e}")

    async def mark_error(self, message: str) -> None:
        """Conveniência: finaliza o run com status ``error``."""
        await self.finish(RunStatus.error, error_message=message)
