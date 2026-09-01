"""IA Brasil — Catálogo público de fontes de coleta (issue #1100).

Combina o registry (``config/sources.yaml`` via ``src/collector/registry.py``)
com os ``IngestionRun`` persistidos para listar, por fonte: nome, coletor,
periodicidade, agenda (cron), última coleta, status do último run, falhas
consecutivas, custo estimado e valor.

Regra: **nunca inventar valor**. ``custo_estimado`` é sempre ``None``
(desconhecido nesta entrega) e ``valor`` vem da descrição declarada no
``sources.yaml`` (None quando ausente).

Uso:
    from src.modules.engagement.fontes import get_catalogo_fontes

    catalogo = await get_catalogo_fontes()
"""

from __future__ import annotations

from datetime import date
from typing import Any

from pydantic import BaseModel

from src.collector.registry import load_registry
from src.modules.collector.config import load_sources
from src.modules.data_quality.service import DataQualityService


class FonteCatalogo(BaseModel):
    """Entrada do catálogo público de fontes.

    Attributes:
        nome: Nome da fonte no ``sources.yaml``.
        coletor: Chave do coletor executável (chave do IngestionRun).
        executavel: True se existe coletor real registrado.
        agenda_cron: Expressão cron declarada.
        periodicidade: Cadência declarada (ex.: '2x/ano', 'manual') ou None.
        ultima_coleta: Data da última coleta terminal (success/partial/error).
        dias_desde_coleta: Dias desde a última coleta (None sem coleta).
        status_ultimo_run: Status terminal do último run (success/partial/error).
        falhas_consecutivas: Número de falhas consecutivas (reset a cada sucesso).
        custo_estimado: Custo estimado de coleta — sempre None (desconhecido).
        valor: Descrição/valor declarado no ``sources.yaml`` (None se ausente).
    """

    nome: str
    coletor: str
    executavel: bool
    agenda_cron: str
    periodicidade: str | None = None
    ultima_coleta: date | None = None
    dias_desde_coleta: int | None = None
    status_ultimo_run: str | None = None
    falhas_consecutivas: int = 0
    custo_estimado: float | None = None
    valor: str | None = None


def _consecutive_failures(runs: list[Any]) -> int:
    """Conta falhas consecutivas (contíguas, resetadas a cada sucesso).

    Args:
        runs: Runs de uma fonte em ordem cronológica.

    Returns:
        Número de runs ``error`` consecutivos desde o último ``success``.
    """
    failures = 0
    for run in runs:
        if run.status == "success":
            failures = 0
        elif run.status == "error":
            failures += 1
    return failures


def _declared_periodicity(run: Any) -> str | None:
    """Lê a cadência declarada persistida no run (issue #1103).

    O scheduler grava ``periodicidade`` ("2x/ano" ou "manual") no
    ``metadata_json`` do último run terminal.

    Args:
        run: Último run terminal da fonte (None quando não há runs).

    Returns:
        Cadência declarada como string, ou None quando desconhecida.
    """
    if run is None:
        return None
    metadata = run.metadata_json or {}
    periodicidade = metadata.get("periodicidade")
    if not isinstance(periodicidade, str) or not periodicidade:
        return None
    return periodicidade


async def get_catalogo_fontes() -> list[FonteCatalogo]:
    """Constrói o catálogo público de fontes (registry + runs).

    Returns:
        Lista de ``FonteCatalogo`` na ordem declarada no ``sources.yaml``,
        incluindo fontes desabilitadas (marcadas como não executáveis).
    """
    entries = load_registry()
    configs = {cfg.name: cfg for cfg in load_sources()}
    runs_by_source = await DataQualityService._load_runs_by_source()
    freshness = await DataQualityService.get_freshness_info()
    freshness_by_source = {item.source: item for item in freshness}

    today = date.today()
    catalogo: list[FonteCatalogo] = []
    for entry in entries:
        runs = runs_by_source.get(entry.collector_name, [])
        terminal_runs = DataQualityService._terminal_runs(runs)
        last_run = terminal_runs[-1] if terminal_runs else None

        info = freshness_by_source.get(entry.collector_name)

        ultima_coleta: date | None = None
        if info is not None and info.last_collection is not None:
            ultima_coleta = info.last_collection
        elif last_run is not None and last_run.started_at is not None:
            ultima_coleta = last_run.started_at.date()

        dias_desde_coleta = (today - ultima_coleta).days if ultima_coleta else None

        config = configs.get(entry.name)
        catalogo.append(
            FonteCatalogo(
                nome=entry.name,
                coletor=entry.collector_name,
                executavel=entry.enabled,
                agenda_cron=entry.schedule,
                periodicidade=_declared_periodicity(last_run),
                ultima_coleta=ultima_coleta,
                dias_desde_coleta=dias_desde_coleta,
                status_ultimo_run=last_run.status if last_run is not None else None,
                falhas_consecutivas=(
                    info.consecutive_failures if info is not None else _consecutive_failures(runs)
                ),
                # Custo estimado: desconhecido nesta entrega — nunca inventar.
                custo_estimado=None,
                valor=config.description if config is not None else None,
            )
        )
    return catalogo


__all__ = ["FonteCatalogo", "get_catalogo_fontes"]
