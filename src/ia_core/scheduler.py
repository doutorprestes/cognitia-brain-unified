"""IA Brasil — APScheduler integration.

Lê config/sources.yaml (via registry único de fontes) e executa coletores
conforme schedules cron. Integra com FastAPI lifespan para iniciar/parar
automaticamente. Fontes declaradas sem coletor executável são logadas como
desabilitadas, sem quebrar o agendamento das demais.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from loguru import logger

from src.collector.registry import load_registry

# Scheduler global (singleton via dict para evitar PLW0603)
_state: dict[str, AsyncIOScheduler | None] = {"scheduler": None}


def get_scheduler() -> AsyncIOScheduler:
    """Retorna o scheduler global (cria se necessário)."""
    if _state["scheduler"] is None:
        _state["scheduler"] = AsyncIOScheduler(
            timezone="America/Sao_Paulo",
            job_defaults={
                "coalesce": True,  # Junta execuções perdidas em 1
                "max_instances": 1,  # Não rodar a mesma fonte em paralelo
                "misfire_grace_time": 3600,  # 1h de tolerância para jobs atrasados
            },
        )
    return _state["scheduler"]


async def run_source_job(source_name: str) -> dict[str, Any]:
    """Executa a coleta de uma fonte específica.

    Esta função é chamada pelo APScheduler conforme o cron de cada fonte.
    Integra com CollectorScheduler para execução e IngestionRun para persistência.
    """
    from src.collector.scheduler import CollectorScheduler

    logger.info(f"[Scheduler] Iniciando coleta: {source_name}")
    start = datetime.now()

    try:
        scheduler = CollectorScheduler()
        result = await scheduler.run_source(source_name)

        elapsed = (datetime.now() - start).total_seconds()
        status = result.get("status", "unknown")
        items = len(result.get("data", {}))

        logger.info(
            f"[Scheduler] {source_name} concluído em {elapsed:.1f}s: status={status}, items={items}"
        )

        # Notificar via Telegram (se configurado)
        await _notify_collection_result(source_name, result, elapsed)

        return result

    except Exception as e:
        elapsed = (datetime.now() - start).total_seconds()
        logger.error(f"[Scheduler] {source_name} falhou após {elapsed:.1f}s: {e}")
        await _notify_collection_error(source_name, e, elapsed)
        return {"source": source_name, "status": "error", "error": str(e)}


async def _notify_collection_result(source: str, result: dict[str, Any], elapsed: float) -> None:
    """Envia notificação Telegram sobre resultado da coleta."""
    import os

    token = os.getenv("TELEGRAM_BOT_TOKEN")
    chat_id = os.getenv("TELEGRAM_CHAT_ID")
    if not token or not chat_id:
        return

    status = result.get("status", "unknown")
    emoji = "✅" if status == "success" else "⚠️"
    items = len(result.get("data", {}))

    message = f"{emoji} Coleta {source}\nStatus: {status}\nItems: {items}\nTempo: {elapsed:.1f}s"

    try:
        import httpx

        async with httpx.AsyncClient() as client:
            await client.post(
                f"https://api.telegram.org/bot{token}/sendMessage",
                json={"chat_id": chat_id, "text": message, "parse_mode": "HTML"},
                timeout=10,
            )
    except Exception:
        pass  # Falha silenciosa em notificação


async def _notify_collection_error(source: str, error: Exception, elapsed: float) -> None:
    """Envia notificação Telegram sobre erro na coleta."""
    import os

    token = os.getenv("TELEGRAM_BOT_TOKEN")
    chat_id = os.getenv("TELEGRAM_CHAT_ID")
    if not token or not chat_id:
        return

    message = f"❌ Erro na coleta {source}\nErro: {str(error)[:200]}\nTempo: {elapsed:.1f}s"

    try:
        import httpx

        async with httpx.AsyncClient() as client:
            await client.post(
                f"https://api.telegram.org/bot{token}/sendMessage",
                json={"chat_id": chat_id, "text": message, "parse_mode": "HTML"},
                timeout=10,
            )
    except Exception:
        pass


def setup_scheduler() -> bool:
    """Configura e inicia o scheduler com todas as fontes de sources.yaml.

    Deve ser chamado no lifespan do FastAPI.

    Retorna ``True`` se o scheduler foi iniciado com sucesso (pelo menos uma
    fonte registrada), ``False`` caso contrário. O retorno permite ao chamador
    decidir se o fallback legado de coleta deve ser ativado, evitando coleta
    duplicada quando o APScheduler está ativo.
    """
    scheduler = get_scheduler()

    try:
        entries = load_registry()
        enabled = [entry for entry in entries if entry.enabled]
        disabled = [entry for entry in entries if not entry.enabled]
    except Exception as e:
        logger.error(f"[Scheduler] Erro ao carregar registry de fontes: {e}")
        return False

    for entry in disabled:
        logger.warning(f"[Scheduler] Fonte '{entry.name}' desabilitada: {entry.disabled_reason}")
    logger.info(f"[Scheduler] Registry: {len(enabled)} executáveis, {len(disabled)} desabilitadas")

    registered = 0
    for entry in enabled:
        try:
            trigger = CronTrigger.from_crontab(entry.schedule)
            scheduler.add_job(
                run_source_job,
                trigger=trigger,
                args=[entry.collector_name],
                id=entry.name,
                name=f"coleta:{entry.name}",
                replace_existing=True,
            )
            registered += 1
            logger.info(
                f"[Scheduler] Registrado: {entry.name} → {entry.collector_name} "
                f"(cron: {entry.schedule})"
            )

        except Exception as e:
            logger.error(f"[Scheduler] Erro ao registrar {entry.name}: {e}")

    if registered > 0:
        scheduler.start()
        logger.info(f"[Scheduler] Iniciado com {registered} fontes agendadas")

        # Loga próximas execuções
        for job in scheduler.get_jobs():
            next_run = job.next_run_time
            if next_run:
                logger.info(f"[Scheduler] {job.id}: próxima execução em {next_run}")

        # Registrar scanner semanal de novas fontes (domingo às 2h)
        _register_source_scanner(scheduler)
        return True
    logger.warning("[Scheduler] Nenhuma fonte registrada — scheduler não iniciado")
    return False


async def _run_source_scan() -> None:
    """Executa scan semanal de novas fontes (chamado pelo scheduler)."""
    try:
        from src.collector.source_discovery import SourceDiscovery

        discovery = SourceDiscovery()
        candidates = await discovery.run_weekly_scan()
        logger.info(f"[Discovery] Scan concluído: {len(candidates)} candidatos")
    except Exception as e:
        logger.error(f"[Discovery] Erro no scan semanal: {e}")


def _register_source_scanner(scheduler: AsyncIOScheduler) -> None:
    """Registra scanner semanal de novas fontes (domingo às 2h)."""
    try:
        trigger = CronTrigger(day_of_week="sun", hour=2, minute=0)
        scheduler.add_job(
            _run_source_scan,
            trigger=trigger,
            id="source_discovery",
            name="scan:novas_fontes",
            replace_existing=True,
        )
        logger.info("[Scheduler] Scanner de novas fontes registrado (domingo às 2h)")
    except Exception as e:
        logger.error(f"[Scheduler] Erro ao registrar scanner: {e}")


def shutdown_scheduler() -> None:
    """Para o scheduler gracefully."""
    scheduler = _state["scheduler"]
    if scheduler and scheduler.running:
        scheduler.shutdown(wait=False)
        logger.info("[Scheduler] Parado")
        _state["scheduler"] = None


def get_next_runs() -> list[dict[str, Any]]:
    """Retorna as próximas execuções agendadas (para dashboard/debug)."""
    scheduler = get_scheduler()
    jobs = scheduler.get_jobs()
    return [
        {
            "id": job.id,
            "name": job.name,
            "next_run": job.next_run_time.isoformat() if job.next_run_time else None,
            "trigger": str(job.trigger),
        }
        for job in jobs
    ]
