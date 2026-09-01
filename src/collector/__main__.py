"""IA Brasil — CLI para execução do coletor de dados.

Este módulo implementa a interface de linha de comando para executar
o coletor de dados para fontes específicas.

Uso:
    python -m src.collector --source cgu
    python -m src.collector --source dados_gov_br
    python -m src.collector --source dou
    python -m src.collector --source mcti
    python -m src.collector --all
    python -m src.collector reingestion --days 7
"""

import asyncio

import typer
from loguru import logger

from src.collector.scheduler import CollectorScheduler

app = typer.Typer()


@app.command()
def run(
    source: str | None = typer.Option(
        None,
        "--source",
        "-s",
        help="Fonte de dados a ser executada (cgu, dados_gov_br, dou, mcti)",
    ),
    all_sources: bool = typer.Option(
        False,
        "--all",
        "-a",
        help="Executar todas as fontes de dados",
    ),
) -> None:
    """Executa a coleta de dados para a fonte especificada.

    Args:
        source: Nome da fonte de dados
        all_sources: Se True, executa todas as fontes
    """
    if not source and not all_sources:
        logger.error("Você deve especificar uma fonte com --source ou --all para executar todas")
        raise typer.Exit(code=1)

    if source and all_sources:
        logger.error("Você não pode especificar --source e --all ao mesmo tempo")
        raise typer.Exit(code=1)

    asyncio.run(main(source, all_sources))


async def main(source: str | None, all_sources: bool) -> None:
    """Função principal para executar a coleta de dados.

    Args:
        source: Nome da fonte de dados
        all_sources: Se True, executa todas as fontes
    """
    scheduler = CollectorScheduler()

    if all_sources:
        logger.info("Executando coleta de dados para todas as fontes...")
        results = await scheduler.run_all_sources()

        for result in results:
            logger.info(f"Fonte: {result['source']}")
            logger.info(f"Status: {result['status']}")
            if result["status"] == "error":
                logger.error(f"Erro: {result.get('error', 'Desconhecido')}")
            logger.info("-" * 50)
    else:
        logger.info(f"Executando coleta de dados para a fonte: {source}")
        assert source is not None  # mypy: else branch garante que source foi passado
        result = await scheduler.run_source(source)

        logger.info(f"Status: {result['status']}")
        if result["status"] == "error":
            logger.error(f"Erro: {result.get('error', 'Desconhecido')}")
        else:
            logger.info(f"Dados coletados: {len(result.get('data', {}))} itens")
            logger.info(f"Registros de proveniência: {len(result.get('provenance', []))}")


@app.command()
def reingestion(
    days: int = typer.Option(
        7,
        "--days",
        "-d",
        help="Número de dias retroativos para coleta",
    ),
    sections: str = typer.Option(
        "1,2",
        "--sections",
        "-s",
        help="Seções do DOU separadas por vírgula",
    ),
) -> None:
    """Executa re-ingestão periódica com versionamento.

    Coleta dados recentes do DOU e registra histórico de extrações.
    """
    section_list = [int(s.strip()) for s in sections.split(",")]
    asyncio.run(_run_reingestion(days, section_list))


async def _run_reingestion(days: int, sections: list[int]) -> None:
    """Executa re-ingestão periódica com notificações.

    Args:
        days: Dias retroativos para coleta
        sections: Lista de seções do DOU
    """
    from src.collector.notification import Notifier
    from src.collector.reingestion import ReingestionOrchestrator

    notifier = Notifier.from_env()
    orchestrator = ReingestionOrchestrator(notifier=notifier)
    report = await orchestrator.run_weekly_reingestion(days=days, sections=sections)
    logger.info(report.summary())


if __name__ == "__main__":
    app()
