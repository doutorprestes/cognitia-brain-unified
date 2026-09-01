"""IA Brasil — Catálogo de Dados Abertos (DCAT-3 JSON-LD) e Data Package.

Issue #1101 — Catálogo de dados DCAT-3 (JSON-LD) + Frictionless Data Package
+ URIs canônicas (padrão 5 estrelas ★★★★).

Entregas:
- ``GET /api/v1/catalog.json`` — catálogo DCAT-3 JSON-LD (``dcat:Catalog``)
  com um ``dcat:Dataset`` por fonte do registry (``config/sources.yaml``),
  enriquecido com dados do último ``IngestionRun`` bem-sucedido
  (``dct:modified``, checksum SHA-256 e ``dcat:accrualPeriodicity`` quando
  disponíveis e inequívocos).
- ``GET /api/v1/export/acoes.datapackage.json`` — Frictionless Data Package
  (``datapackage.json``) descrevendo o schema tabular de ``acoes.csv``.

Nenhum valor é inventado: campos sem fonte de verdade no registro são omitidos.

Convenção de URIs canônicas (5 estrelas, base = ``settings.public_api_url``):
    {base}/api/v1/pbia/acoes/{id}      — ação
    {base}/api/v1/pbia/eixos/{id}      — eixo
    {base}/api/v1/pbia/programas/{id}  — programa
    {base}/api/v1/pbia/planos/{id}     — plano
    {base}/api/v1/evidencias/{id}      — evidência (endpoint autenticado)
    {base}/api/v1/export/acoes.csv     — distribuição tabular (CSV)
    {base}/api/v1/export/acoes.json    — distribuição tabular (JSON)
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from loguru import logger
from sqlalchemy import select

from src.collector.raw_store import RAW_CHECKSUM_KEY
from src.collector.registry import SourceEntry, load_registry
from src.core.db import IngestionRun
from src.core.db import settings as app_settings
from src.core.json_encoder import dumps_with_encoder
from src.core.limiter import RATE_LIMIT_PUBLIC_READ, limiter
from src.modules.collector.config import SourceConfig, load_sources
from src.modules.export.service import get_db

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

router = APIRouter(tags=["catalog"])

# ---------------------------------------------------------------------------
# Constantes DCAT-3 / Frictionless
# ---------------------------------------------------------------------------

# @context mínimo e válido (namespaces + coerções de tipo) conforme DCAT-3 (W3C REC 2024).
DCAT_CONTEXT: dict[str, Any] = {
    "dcat": "http://www.w3.org/ns/dcat#",
    "dct": "http://purl.org/dc/terms/",
    "foaf": "http://xmlns.com/foaf/0.1/",
    "spdx": "http://spdx.org/rdf/terms#",
    "xsd": "http://www.w3.org/2001/XMLSchema#",
    "dct:issued": {"@type": "xsd:dateTime"},
    "dct:modified": {"@type": "xsd:dateTime"},
    "dcat:accessURL": {"@type": "@id"},
    "dcat:downloadURL": {"@type": "@id"},
    "dcat:landingPage": {"@type": "@id"},
    "spdx:checksumAlgorithm": {"@type": "@id"},
}

# Algoritmo SHA-256 como compact IRI do vocabulário SPDX (expande via prefixo spdx).
SPDX_SHA256_ALGORITHM = "spdx:checksumAlgorithm_sha256"

# Tipos das colunas do export tabular (Frictionless Data Package).
DATAPACKAGE_FIELD_TYPES: dict[str, str] = {
    "eixo_codigo": "integer",
    "eixo_nome": "string",
    "programa_nome": "string",
    "acao_codigo": "string",
    "acao_nome": "string",
    "status_atual": "string",
    "data_avaliacao": "date",
    "instituicoes": "string",
    "meta_count": "integer",
    "source_ref": "string",
}

_URI_CONVENTION_NOTICE = (
    "URIs canônicas (padrão 5 estrelas ★★★★): "
    "ação {base}/api/v1/pbia/acoes/{{id}}; eixo {base}/api/v1/pbia/eixos/{{id}}; "
    "programa {base}/api/v1/pbia/programas/{{id}}; plano {base}/api/v1/pbia/planos/{{id}}; "
    "evidência {base}/api/v1/evidencias/{{id}} (endpoint autenticado). "
    "Distribuições tabulares: {base}/api/v1/export/acoes.csv e "
    "{base}/api/v1/export/acoes.json."
)


# ---------------------------------------------------------------------------
# Funções puras (testáveis sem banco)
# ---------------------------------------------------------------------------


def _utc_now_iso() -> str:
    """Timestamp UTC atual em ISO 8601 (para ``dct:issued``/``dct:modified``)."""
    return datetime.now(UTC).isoformat()


def cron_to_periodicity(schedule: str) -> str | None:
    """Converte padrões simples de cron em intervalo ISO 8601 (accrualPeriodicity).

    Apenas padrões inequívocos são mapeados (diário/semanal/mensal/anual);
    qualquer outra expressão retorna ``None`` e o campo fica de fora do DCAT.

    Args:
        schedule: Expressão cron de 5 campos da fonte (``config/sources.yaml``).

    Returns:
        Intervalo de recorrência ISO 8601 (ex.: ``R/P1W``) ou ``None``.
    """
    parts = schedule.split()
    if len(parts) != 5:
        return None
    minute, _, dom, month, dow = parts
    if minute != "0":
        return None
    # Rejeita expressões compostas (listas, intervalos, passos) — o mapeamento
    # só cobre padrões inequívocos; demais ficam de fora do catálogo.
    for field in (dom, month, dow):
        if not field.isdigit() and field != "*":
            return None
    if dom == "*" and month == "*" and dow == "*":
        return "R/P1D"
    if dom == "*" and month == "*" and dow != "*":
        return "R/P1W"
    if dom != "*" and month == "*" and dow == "*":
        return "R/P1M"
    if dom != "*" and month != "*" and dow == "*":
        return "R/P1Y"
    return None


def _checksum_from_run(run: IngestionRun) -> dict[str, Any] | None:
    """Checksum SPDX a partir de ``IngestionRun.metadata_json`` quando existir.

    Args:
        run: Registro do último run bem-sucedido da fonte.

    Returns:
        Objeto ``spdx:Checksum`` ou ``None`` quando não há checksum preservado.
    """
    raw_checksum = (run.metadata_json or {}).get(RAW_CHECKSUM_KEY)
    if not isinstance(raw_checksum, str) or not raw_checksum:
        return None
    return {
        "@type": "spdx:Checksum",
        "spdx:checksumValue": raw_checksum,
        "spdx:checksumAlgorithm": SPDX_SHA256_ALGORITHM,
    }


def _build_distributions(base_url: str) -> list[dict[str, Any]]:
    """Distribuições CSV/JSON (dados abertos) do portal para cada dataset."""
    distributions: list[dict[str, Any]] = []
    for filename, media_type in (
        ("acoes.csv", "text/csv"),
        ("acoes.json", "application/json"),
    ):
        distributions.append(
            {
                "@type": "dcat:Distribution",
                "dcat:accessURL": f"{base_url}/api/v1/export/{filename}",
                "dcat:mediaType": media_type,
                "dct:format": "csv" if filename.endswith(".csv") else "json",
            }
        )
    return distributions


def _build_dataset(
    entry: SourceEntry,
    config: SourceConfig | None,
    run: IngestionRun | None,
    base_url: str,
) -> dict[str, Any]:
    """Constrói um ``dcat:Dataset`` para uma fonte do registry.

    Args:
        entry: Fonte do registry (``SourceEntry``).
        config: Config declarada no ``sources.yaml`` (descrição/URL) quando existe.
        run: Último ``IngestionRun`` bem-sucedido da fonte (opcional).
        base_url: URL pública da API (base das URIs canônicas).

    Returns:
        Dicionário JSON-LD do dataset.
    """
    title = config.description if config and config.description else entry.name
    dataset: dict[str, Any] = {
        "@id": f"{base_url}/api/v1/catalog.json#dataset-{entry.name}",
        "@type": "dcat:Dataset",
        "dct:identifier": entry.name,
        "dct:title": title,
    }
    if config and config.description:
        dataset["dct:description"] = config.description
    if run is not None:
        modified = run.finished_at or run.started_at
        dataset["dct:modified"] = modified.isoformat()
        checksum = _checksum_from_run(run)
        if checksum is not None:
            dataset["spdx:checksum"] = checksum
    periodicity = cron_to_periodicity(entry.schedule)
    if periodicity is not None:
        dataset["dcat:accrualPeriodicity"] = periodicity
    if config is not None and config.url:
        dataset["dcat:landingPage"] = config.url
    dataset["dcat:distribution"] = _build_distributions(base_url)
    return dataset


def build_catalog_jsonld(
    *,
    entries: list[SourceEntry],
    configs: dict[str, SourceConfig],
    latest_runs: dict[str, IngestionRun],
    base_url: str,
) -> dict[str, Any]:
    """Constrói o catálogo DCAT-3 JSON-LD completo (função pura).

    Args:
        entries: Fontes executáveis do registry.
        configs: Configs do ``sources.yaml`` por nome de fonte.
        latest_runs: Último run bem-sucedido por ``collector_name``.
        base_url: URL pública da API.

    Returns:
        Dicionário JSON-LD do ``dcat:Catalog``.
    """
    datasets = [
        _build_dataset(
            entry,
            configs.get(entry.name),
            latest_runs.get(entry.collector_name),
            base_url,
        )
        for entry in entries
    ]
    now = _utc_now_iso()
    return {
        "@context": DCAT_CONTEXT,
        "@id": f"{base_url}/api/v1/catalog.json",
        "@type": "dcat:Catalog",
        "dct:identifier": "ia-brasil-catalog",
        "dct:title": "Catálogo de Dados Abertos — IA Brasil / PBIA",
        "dct:description": (
            "Catálogo DCAT-3 (JSON-LD) dos conjuntos de dados coletados e "
            "exportados pelo portal IA Brasil (monitoramento do PBIA).\n"
            + _URI_CONVENTION_NOTICE.format(base=base_url)
        ),
        "dct:publisher": {"@id": base_url, "foaf:name": "IA Brasil"},
        "dct:issued": now,
        "dct:modified": now,
        "dct:conformsTo": {
            "@id": "http://www.w3.org/ns/dcat#",
            "dct:title": "DCAT Version 3",
        },
        "dcat:dataset": datasets,
    }


def build_datapackage_json(
    headers: list[str],
    *,
    base_url: str,
    count: int | None = None,
) -> dict[str, Any]:
    """Constrói um Frictionless Data Package (``datapackage.json``).

    Args:
        headers: Colunas do export tabular (``CSV_ACOES_HEADERS`` ou schema real).
        base_url: URL pública da API (homepage da distribuição).
        count: Número de linhas do CSV (opcional).

    Returns:
        Dicionário do Data Package conforme ``profile: tabular-data-package``.
    """
    fields = [
        {"name": header, "type": DATAPACKAGE_FIELD_TYPES.get(header, "string")}
        for header in headers
    ]
    resource: dict[str, Any] = {
        "name": "acoes",
        "title": "Ações do PBIA",
        "path": "acoes.csv",
        "profile": "tabular-data-resource",
        "format": "csv",
        "mediatype": "text/csv",
        "encoding": "utf-8-sig",
        "schema": {"fields": fields, "missingValues": [""]},
    }
    if count is not None:
        resource["rowCount"] = count
    return {
        "profile": "tabular-data-package",
        "name": "ia-brasil-acoes",
        "title": "Ações do PBIA",
        "description": "Exportação tabular das ações do PBIA (dados abertos, 5 estrelas).",
        "homepage": f"{base_url}/api/v1/export/acoes.csv",
        "licenses": [
            {
                "name": "MIT",
                "path": "https://opensource.org/license/mit",
                "title": "MIT License",
            }
        ],
        "resources": [resource],
    }


# ---------------------------------------------------------------------------
# Acesso a dados (banco + registry)
# ---------------------------------------------------------------------------


async def _latest_runs(session: AsyncSession) -> dict[str, IngestionRun]:
    """Último run bem-sucedido por fonte (uma consulta, ordem decrescente).

    Args:
        session: Sessão assíncrona do banco.

    Returns:
        Mapa ``collector_name → IngestionRun`` (mais recente por fonte).
    """
    result = await session.execute(
        select(IngestionRun)
        .where(IngestionRun.status == "success")
        .order_by(IngestionRun.started_at.desc(), IngestionRun.id.desc())
    )
    latest: dict[str, IngestionRun] = {}
    for run in result.scalars().all():
        latest.setdefault(run.source, run)
    return latest


async def build_catalog(session: AsyncSession, base_url: str) -> dict[str, Any]:
    """Carrega registry + runs e constrói o catálogo DCAT-3 JSON-LD.

    Args:
        session: Sessão assíncrona do banco.
        base_url: URL pública da API (base das URIs canônicas).

    Returns:
        Dicionário JSON-LD do ``dcat:Catalog``.
    """
    entries = [entry for entry in load_registry() if entry.enabled]
    configs = {cfg.name: cfg for cfg in load_sources()}
    latest_runs = await _latest_runs(session)
    return build_catalog_jsonld(
        entries=entries,
        configs=configs,
        latest_runs=latest_runs,
        base_url=base_url.rstrip("/"),
    )


# ---------------------------------------------------------------------------
# Endpoint público
# ---------------------------------------------------------------------------


@router.get("/catalog.json")
@limiter.limit(RATE_LIMIT_PUBLIC_READ)
async def catalog_jsonld(
    request: Request,
    session: AsyncSession = Depends(get_db),
) -> Response:
    """Catálogo DCAT-3 JSON-LD dos datasets coletados (público, issue #1101).

    Returns:
        JSON-LD ``application/ld+json`` com um ``dcat:Dataset`` por fonte.
    """
    try:
        payload = await build_catalog(session, app_settings.public_api_url)
    except Exception:
        logger.error("Falha ao gerar catálogo DCAT-3", exc_info=True)
        raise HTTPException(status_code=500, detail="Erro ao gerar catálogo de dados")
    return Response(
        content=dumps_with_encoder(payload, indent=2),
        media_type="application/ld+json",
        headers={
            "Cache-Control": "public, max-age=3600",
            "Content-Disposition": 'attachment; filename="catalog.json"',
        },
    )
