"""IA Brasil — Registry único de fontes de coleta.

Valida `config/sources.yaml` contra os coletores reais em
`src/collector/sources/*` e produz a lista de fontes executáveis.

Fontes declaradas sem coletor real são marcadas como não executáveis
(com motivo), sem serem removidas do YAML. Este módulo é a única fonte
de verdade para o agendamento (APScheduler) e para o `CollectorScheduler`.

Uso:
    from src.collector.registry import load_registry, collector_classes

    entries = load_registry()
    classes = collector_classes()  # {chave_do_coletor: classe}
"""

from __future__ import annotations

import importlib
from dataclasses import dataclass

from loguru import logger

from src.collector.sources.cgee_relatorio import CgeeRelatorioCollector
from src.collector.sources.cgu_portal_transparencia import CGUCollector
from src.collector.sources.dados_gov_br import DadosGovBRCollector
from src.collector.sources.dou_scraper import DOUScraper
from src.collector.sources.mcti_monitor import MCTIMonitorCollector
from src.collector.sources.mcti_noticias import MCTICollector
from src.collector.sources.obia import OBIACollector
from src.collector.sources.pbia_cgee import PbiaCgeeCollector
from src.collector.sources.pbia_powerbi import PBIAPowerBIScraper
from src.modules.collector.config import SourceConfig, load_sources

# ---------------------------------------------------------------------------
# Mapeamento canônico: nome no sources.yaml → (chave no CollectorScheduler,
# classe do coletor real em src/collector/sources/*).
# ---------------------------------------------------------------------------

YAML_TO_COLLECTOR: dict[str, tuple[str, type]] = {
    "pbia_cgee": ("pbia_cgee", PbiaCgeeCollector),
    "cgee_relatorio": ("cgee_relatorio", CgeeRelatorioCollector),
    "mcti_monitor": ("mcti_monitor", MCTIMonitorCollector),
    "pbia_powerbi": ("pbia_powerbi", PBIAPowerBIScraper),
    "obia": ("obia", OBIACollector),
    "dou_atos": ("dou", DOUScraper),
    "dadosgov_datasets": ("dados_gov_br", DadosGovBRCollector),
    "cgu": ("cgu", CGUCollector),
    "mcti_noticias": ("mcti", MCTICollector),
}


@dataclass(frozen=True)
class SourceEntry:
    """Fonte declarada no sources.yaml resolvida contra coletores reais.

    Attributes:
        name: Nome da fonte no sources.yaml.
        collector_name: Chave usada pelo CollectorScheduler/APScheduler.
        schedule: Cron da fonte.
        enabled: True se existe coletor real executável.
        disabled_reason: Motivo da desabilitação (quando ``enabled`` é False).
        collector_class: Classe do coletor real (None quando desabilitada).
    """

    name: str
    collector_name: str
    schedule: str
    enabled: bool
    disabled_reason: str | None = None
    collector_class: type | None = None


def _import_class(parser: str) -> type | None:
    """Importa a classe declarada no parser (``modulo:Classe``)."""
    module_name, _, attr = parser.partition(":")
    if not attr:
        return None
    try:
        module = importlib.import_module(module_name)
    except ImportError as e:
        logger.warning(f"[Registry] Módulo '{module_name}' não importável: {e}")
        return None
    obj = getattr(module, attr, None)
    if isinstance(obj, type):
        return obj
    logger.warning(f"[Registry] '{attr}' não é uma classe em '{module_name}'")
    return None


def _resolve_entry(config: SourceConfig) -> SourceEntry:
    """Resolve uma fonte declarada em executável ou desabilitada com motivo."""
    if not config.enabled:
        reason = config.disabled_reason or "marcada como desabilitada no sources.yaml"
        return SourceEntry(
            name=config.name,
            collector_name=config.name,
            schedule=config.schedule,
            enabled=False,
            disabled_reason=reason,
        )

    known = YAML_TO_COLLECTOR.get(config.name)
    cls = _import_class(config.parser)

    if cls is None and known is not None:
        # parser antigo/inexistente no YAML, mas há coletor real mapeado
        logger.warning(
            f"[Registry] '{config.name}': parser '{config.parser}' não importável — "
            f"usando coletor real {known[1].__name__}"
        )
        collector_name, cls = known
    elif cls is None:
        reason = (
            f"sem coletor executável: parser '{config.parser}' não importável "
            "e nenhum coletor em src/collector/sources"
        )
        return SourceEntry(
            name=config.name,
            collector_name=config.name,
            schedule=config.schedule,
            enabled=False,
            disabled_reason=reason,
        )
    else:
        collector_name = known[0] if known is not None else config.name
        if known is not None and known[1] is not cls:
            logger.warning(
                f"[Registry] '{config.name}': parser aponta para {cls.__name__}, "
                f"mapeado para {known[1].__name__}"
            )

    return SourceEntry(
        name=config.name,
        collector_name=collector_name,
        schedule=config.schedule,
        enabled=True,
        collector_class=cls,
    )


def load_registry(path: str = "config/sources.yaml") -> list[SourceEntry]:
    """Carrega o registry completo (declaradas = executáveis + desabilitadas).

    Args:
        path: Caminho do sources.yaml (respeita ``IA_BRASIL_CONFIG``).

    Returns:
        Lista de ``SourceEntry`` na ordem declarada no YAML.
    """
    entries: list[SourceEntry] = []
    for config in load_sources(path):
        entry = _resolve_entry(config)
        entries.append(entry)
        if entry.enabled:
            logger.info(
                f"[Registry] {entry.name} → coletor {entry.collector_name} (cron: {entry.schedule})"
            )
        else:
            logger.warning(f"[Registry] {entry.name} desabilitada: {entry.disabled_reason}")
    return entries


def enabled_entries(path: str = "config/sources.yaml") -> list[SourceEntry]:
    """Retorna apenas as fontes executáveis do registry."""
    return [entry for entry in load_registry(path) if entry.enabled]


def disabled_entries(path: str = "config/sources.yaml") -> list[SourceEntry]:
    """Retorna as fontes declaradas porém não executáveis (com motivo)."""
    return [entry for entry in load_registry(path) if not entry.enabled]


def collector_classes() -> dict[str, type]:
    """Retorna mapeamento chave do coletor → classe para o CollectorScheduler."""
    classes: dict[str, type] = {}
    for entry in load_registry():
        if entry.enabled and entry.collector_class is not None:
            classes[entry.collector_name] = entry.collector_class
    return classes
