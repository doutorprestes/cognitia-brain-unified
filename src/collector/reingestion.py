"""IA Brasil — Re-ingestion Pipeline.

Pipeline de re-ingestão periódica que integra o DOU scraper com o
pipeline de ingestão do PBIA. Suporta versionamento de extrações,
detecção de mudanças e notificações.

Uso:
    from src.collector.reingestion import ReingestionPipeline

    pipeline = ReingestionPipeline()
    report = await pipeline.run(source="dou", days=7)
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from loguru import logger
from sqlalchemy import select

from src.collector.hashing import stable_hash
from src.collector.notification import Notifier
from src.collector.raw_store import (
    PARSER_VERSION_KEY,
    QUARANTINE_REASON_KEY,
    RAW_CHECKSUM_KEY,
    RAW_KIND_KEY,
    RAW_PATH_KEY,
    RAW_SIZE_KEY,
    save_raw,
)
from src.collector.sources.dou_scraper import DOUScraper
from src.collector.versioning import persist_item
from src.core.db import (
    IngestionRun,
    TipoEvidencia,
    get_session,
)


class ReingestionReport:
    """Relatório de uma execução de re-ingestão.

    Attributes:
        run_id: ID único da execução
        source: Fonte de dados coletada
        status: Status da execução (running, success, error)
        items_fetched: Total de itens buscados
        items_new: Itens novos inseridos
        items_updated: Itens atualizados
        items_unchanged: Itens sem alteração
        previous_hash: Hash do estado anterior
        current_hash: Hash do estado novo
        errors: Lista de erros encontrados
        started_at: Data/hora de início
        finished_at: Data/hora de conclusão
    """

    def __init__(self, source: str) -> None:
        self.run_id = str(uuid.uuid4())
        self.source = source
        self.status = "running"
        self.items_fetched = 0
        self.items_new = 0
        self.items_updated = 0
        self.items_unchanged = 0
        self.previous_hash: str | None = None
        self.current_hash: str | None = None
        self.errors: list[str] = []
        self.started_at = datetime.now(UTC)
        self.finished_at: datetime | None = None
        self.metadata: dict[str, Any] = {}

    def mark_success(self) -> None:
        """Marca a execução como bem-sucedida."""
        self.status = "success"
        self.finished_at = datetime.now(UTC)

    def mark_error(self, message: str) -> None:
        """Marca a execução como com erro.

        Args:
            message: Mensagem de erro
        """
        self.status = "error"
        self.errors.append(message)
        self.finished_at = datetime.now(UTC)

    def mark_partial(self, message: str) -> None:
        """Marca a execução como parcial (parse suspeito, sem erro hard).

        Args:
            message: Motivo do status parcial (quarentena)
        """
        self.status = "partial"
        self.errors.append(message)
        self.finished_at = datetime.now(UTC)

    def summary(self) -> str:
        """Retorna um resumo legível do relatório.

        Returns:
            String com o resumo formatado
        """
        lines = [
            "=== Re-ingestion Report ===",
            f"Run ID: {self.run_id}",
            f"Source: {self.source}",
            f"Status: {self.status}",
            f"Started: {self.started_at}",
            f"Finished: {self.finished_at or 'N/A'}",
            "",
            f"Items fetched:  {self.items_fetched}",
            f"Items new:      {self.items_new}",
            f"Items updated:  {self.items_updated}",
            f"Items unchanged:{self.items_unchanged}",
            "",
        ]
        if self.previous_hash:
            lines.append(f"Previous hash: {self.previous_hash[:16]}...")
        if self.current_hash:
            lines.append(f"Current hash:  {self.current_hash[:16]}...")
        if self.errors:
            lines.append("")
            lines.append("Errors:")
            for error in self.errors:
                lines.append(f"  - {error}")
        return "\n".join(lines)


class ReingestionPipeline:
    """Pipeline de re-ingestão periódica.

    Integra o DOU scraper com o pipeline de ingestão, suportando:
    - Versionamento de extrações via hash de conteúdo
    - Detecção de mudanças entre execuções
    - Registro de histórico de execuções no banco
    - Notificações via Telegram quando novos dados são detectados
    """

    def __init__(self, notifier: Notifier | None = None) -> None:
        self.dou_scraper = DOUScraper()
        self.notifier = notifier or Notifier.from_env()

    async def run(
        self,
        source: str = "dou",
        days: int = 7,
        dry_run: bool = False,
        link_after: bool = True,
    ) -> ReingestionReport:
        """Executa o pipeline de re-ingestão.

        Args:
            source: Fonte de dados ('dou' para Diário Oficial)
            days: Número de dias retroativos para buscar
            dry_run: Se True, não persiste no banco
            link_after: Se True, executa o auto-linker após persistir evidências
                novas para vinculá-las a ações (evidências já vinculadas são
                ignoradas pelo próprio auto-linker)

        Returns:
            ReingestionReport com o resultado da execução
        """
        report = ReingestionReport(source)

        logger.info(
            "Starting re-ingestion pipeline",
            source=source,
            days=days,
            dry_run=dry_run,
        )

        try:
            # 1. Buscar estado anterior
            report.previous_hash = await self._get_latest_hash(source)

            # 2. Coletar dados da fonte
            if source == "dou":
                items = await self._collect_dou(days)
            else:
                report.mark_error(f"Unknown source: {source}")
                return report

            report.items_fetched = len(items)
            logger.info(f"Fetched {len(items)} items from {source}")

            # 2b. Preservar payload bruto em disco (imutável) + parser version
            await self._preserve_raw(report, source, items)

            # 3. Calcular hash do estado novo (estável/determinístico)
            report.current_hash = self._compute_hash(items)

            # 4. Detectar mudanças
            if report.previous_hash == report.current_hash:
                report.items_unchanged = report.items_fetched
                logger.info("No changes detected since last ingestion")
            else:
                # Processar cada item
                for item in items:
                    result = await self._process_item(item, dry_run)
                    if result == "new":
                        report.items_new += 1
                    elif result == "updated":
                        report.items_updated += 1
                    else:
                        report.items_unchanged += 1

            # 4b. Quarantine: coleta sem nenhum item (ex.: HTML presente mas
            # parse sem métricas) → run parcial com motivo, sem erro hard.
            if report.items_fetched == 0:
                reason = (
                    "parse retornou zero itens com payload preservado "
                    "(possível mudança de layout da fonte)"
                )
                report.mark_partial(reason)
                report.metadata[QUARANTINE_REASON_KEY] = reason
                await self._persist_run(report, dry_run)
                return report

            # 5. Marcar sucesso e registrar execução no banco
            # (mark_success ANTES de _save_run para persistir com status correto)
            report.mark_success()
            await self._persist_run(report, dry_run)

            # 6. Vincular evidências novas a ações (auto-linker)
            if link_after and not dry_run and report.items_new > 0:
                await self._link_new_evidences(report)

            logger.info(
                "Re-ingestion completed",
                new=report.items_new,
                updated=report.items_updated,
                unchanged=report.items_unchanged,
            )

            # Notificar quando há novos dados
            has_changes = report.items_new > 0 or report.items_updated > 0
            if has_changes:
                await self.notifier.notify_ingestion(report)

        except Exception as e:
            report.mark_error(str(e))
            logger.error(f"Re-ingestion failed: {e}")
            # Persistir o run com status 'error' e a mensagem de erro
            await self._persist_run(report, dry_run)
            await self.notifier.notify_error(str(e))

        return report

    async def _persist_run(
        self,
        report: ReingestionReport,
        dry_run: bool,
    ) -> None:
        """Persiste o run no banco, exceto em modo dry-run.

        Falhas de persistência são logadas mas não propagadas, para que o
        relatório de erro ainda seja retornado ao chamador.

        Args:
            report: Relatório da execução
            dry_run: Se True, não persiste no banco
        """
        if dry_run:
            return
        try:
            await self._save_run(report)
        except Exception as e:
            logger.error(f"Failed to persist run {report.run_id}: {e}")

    @staticmethod
    async def _link_new_evidences(report: ReingestionReport) -> None:
        """Executa o auto-linker para vincular evidências novas a ações.

        O auto-linker processa apenas evidências sem vínculo, então evidências
        já vinculadas não são re-vinculadas. Falhas são logadas mas não
        propagadas — a vinculação é um passo não-crítico da re-ingestão.

        Args:
            report: Relatório da execução em andamento.
        """
        try:
            from src.modules.linking.auto_linker import auto_link

            result = await auto_link()
            report.metadata["auto_link"] = {
                "vinculos_criados": result.vinculos_criados,
                "evidencias_novas": result.evidencias_novas,
            }
            logger.info(
                f"Auto-link após re-ingestão: {result.vinculos_criados} vínculos "
                f"criados para {result.evidencias_novas} evidências novas"
            )
        except Exception as e:
            logger.error(f"Auto-link após re-ingestão falhou: {e}")

    async def _collect_dou(self, days: int) -> list[dict[str, Any]]:
        """Coleta dados do DOU para os últimos N dias.

        Args:
            days: Número de dias retroativos

        Returns:
            Lista de itens coletados do DOU
        """
        all_items: list[dict[str, Any]] = []

        for section in [1, 2]:
            try:
                items = await self.dou_scraper.scrape_recent(section, days=days)
                all_items.extend(items)
            except Exception as e:
                logger.warning(f"Error scraping DOU section {section}: {e}")

        return all_items

    async def _preserve_raw(
        self,
        report: ReingestionReport,
        source: str,
        items: list[dict[str, Any]],
    ) -> None:
        """Preserva o payload bruto em disco e registra o parser version.

        Falhas de disco são logadas mas não propagadas — o pipeline continua
        e o run ainda é persistido (sem os metadados de raw).

        Args:
            report: Relatório da execução em andamento.
            source: Nome da fonte.
            items: Itens coletados (payload bruto do run).
        """
        parser_version = getattr(self.dou_scraper, "PARSER_VERSION", "1.0.0")
        report.metadata[PARSER_VERSION_KEY] = parser_version
        try:
            artifact = save_raw(source, report.run_id, items)
            report.metadata[RAW_PATH_KEY] = artifact.path
            report.metadata[RAW_CHECKSUM_KEY] = artifact.checksum
            report.metadata[RAW_SIZE_KEY] = artifact.size
            report.metadata[RAW_KIND_KEY] = artifact.kind
        except Exception as e:
            logger.warning(f"Falha ao preservar raw do run {report.run_id}: {e}")

    async def _process_item(
        self,
        item: dict[str, Any],
        dry_run: bool,
    ) -> str:
        """Processa um item individual da coleta com versionamento.

        Verifica se o item já existe no banco (via fingerprint de conteúdo)
        e cria nova evidência ou nova versão conforme necessário. Conteúdo
        novo NUNCA atualiza a evidência anterior em lugar — cria uma nova
        ``Evidencia`` (content-addressed), preservando o histórico (issue #1087).

        Args:
            item: Dados do item coletado
            dry_run: Se True, não persiste

        Returns:
            'new' se item novo, 'updated' se nova versão, 'unchanged' se sem mudança
        """
        section = item.get("section", 1)
        day = item.get("date", "")
        url = f"https://www.in.gov.br/leitura/jornal/{day}/secao/{section}"
        content_text = item.get("text", "")
        titulo = f"DOU Seção {section} - {day}"
        data_pub = datetime.strptime(day, "%Y-%m-%d").date() if day else None

        if dry_run:
            return "new"  # Em dry-run, consideramos como novo

        async with get_session() as session:
            return await persist_item(
                session,
                url=url,
                content_text=content_text,
                titulo=titulo,
                instituicao_emissora="Diário Oficial da União",
                tipo_documental="ato_oficial",
                data_publicacao=data_pub,
                tipo_evidencia=TipoEvidencia.ato_oficial.value,
                confianca=0.8,
            )

    @staticmethod
    def _compute_hash(items: list[dict[str, Any]]) -> str:
        """Computa hash determinístico e estável de uma lista de itens.

        Usa ``stable_hash``: normaliza campos voláteis (timestamps de coleta
        embutidos por parsers) e ordena chaves — o hash é estável entre
        execuções para o mesmo conteúdo (issue #1087, D2).

        Args:
            items: Lista de itens para hash

        Returns:
            Hash SHA-256 em hexadecimal (64 chars)
        """
        return stable_hash(items)

    @staticmethod
    async def _get_latest_hash(source: str) -> str | None:
        """Obtém o hash da última execução bem-sucedida.

        Args:
            source: Nome da fonte

        Returns:
            Hash da última execução ou None se não houver
        """
        async with get_session() as session:
            result = await session.execute(
                select(IngestionRun)
                .where(
                    IngestionRun.source == source,
                    IngestionRun.status == "success",
                )
                .order_by(
                    IngestionRun.started_at.desc(),
                    IngestionRun.id.desc(),
                )
                .limit(1)
            )
            last_run = result.scalar_one_or_none()
            return last_run.current_hash if last_run else None

    @staticmethod
    async def _save_run(report: ReingestionReport) -> None:
        """Salva o registro da execução no banco.

        Args:
            report: Relatório da execução
        """
        async with get_session() as session:
            run = IngestionRun(
                id=report.run_id,
                started_at=report.started_at,
                finished_at=report.finished_at,
                source=report.source,
                status=report.status,
                previous_hash=report.previous_hash,
                current_hash=report.current_hash,
                items_fetched=report.items_fetched,
                items_new=report.items_new,
                items_updated=report.items_updated,
                items_unchanged=report.items_unchanged,
                error_message="\n".join(report.errors) if report.errors else None,
                metadata_json=report.metadata,
            )
            session.add(run)
            await session.flush()
            logger.info(f"Ingestion run saved: {report.run_id}")


async def run_reingestion(
    source: str = "dou",
    days: int = 7,
    dry_run: bool = False,
    notifier: Notifier | None = None,
) -> ReingestionReport:
    """Função de conveniência para executar a re-ingestão.

    Args:
        source: Fonte de dados ('dou' para Diário Oficial)
        days: Número de dias retroativos para buscar
        dry_run: Se True, não persiste no banco
        notifier: Instância de Notifier (usa env padrão se None)

    Returns:
        ReingestionReport com o resultado da execução
    """
    pipeline = ReingestionPipeline(notifier=notifier)
    return await pipeline.run(source=source, days=days, dry_run=dry_run)


class ReingestionOrchestrator:
    """Orquestrador de re-ingestão periódica.

    Fornece interface de alto nível para execução de re-ingestão
    semanal, agendada e consulta de histórico de extrações.
    """

    def __init__(self, notifier: Notifier | None = None) -> None:
        self.pipeline = ReingestionPipeline(notifier=notifier)

    async def run_weekly_reingestion(
        self,
        days: int = 7,
        sections: list[int] | None = None,
    ) -> ReingestionReport:
        """Executa re-ingestão semanal do DOU.

        Args:
            days: Número de dias retroativos
            sections: Seções do DOU (reservado para uso futuro)

        Returns:
            ReingestionReport com o resultado
        """
        _ = sections  # reservado para filtrar seções específicas
        return await self.pipeline.run(source="dou", days=days)

    async def run_scheduled_collection(self) -> list[ReingestionReport]:
        """Executa coleta agendada completa de todas as fontes.

        Returns:
            Lista de relatórios por fonte
        """
        reports: list[ReingestionReport] = []

        # DOU via re-ingestão versionada
        dou_report = await self.pipeline.run(source="dou", days=7)
        reports.append(dou_report)

        return reports

    @staticmethod
    async def get_extraction_history(
        source: str | None = None,
        limit: int = 20,
    ) -> list[dict[str, Any]]:
        """Obtém histórico de extrações versionadas.

        Args:
            source: Filtrar por fonte específica (None = todas)
            limit: Número máximo de registros

        Returns:
            Lista de dicts com dados das execuções
        """
        from sqlalchemy import select

        async with get_session() as session:
            query = select(IngestionRun).order_by(IngestionRun.started_at.desc())
            if source:
                query = query.where(IngestionRun.source == source)
            query = query.limit(limit)

            result = await session.execute(query)
            runs = result.scalars().all()

            return [
                {
                    "id": run.id,
                    "source": run.source,
                    "run_date": run.started_at.isoformat(),
                    "status": run.status,
                    "records_created": run.items_new,
                    "records_updated": run.items_updated,
                    "records_unchanged": run.items_unchanged,
                    "previous_hash": run.previous_hash,
                    "current_hash": run.current_hash,
                }
                for run in runs
            ]
