"""IA Brasil — Replay de um run a partir do raw preservado (issue #1087, D5).

Re-executa um ``run_id`` lendo o payload raw do disco e re-aplicando a
lógica de fingerprint/versionamento de ``src/collector/versioning``. O
replay é IDEMPOTENTE: itens já persistidos (mesmo fingerprint) são ignorados,
portanto re-executar o mesmo run não duplica evidências e reproduz o mesmo
resultado (mesmo ``current_hash`` estável).

Uso:
    from src.collector.replay import replay_run

    report = await replay_run(run_id="...")
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from loguru import logger

from src.collector.hashing import stable_hash
from src.collector.raw_store import load_raw
from src.collector.versioning import persist_item
from src.core.db import IngestionRun, get_session

if TYPE_CHECKING:
    from collections.abc import Iterator

    from sqlalchemy.ext.asyncio import AsyncSession


@dataclass
class ReplayReport:
    """Relatório de um replay de run.

    Attributes:
        run_id: ID do novo run criado pelo replay.
        source: Fonte do run original.
        replay_of: ID do run original re-executado.
        status: Status do replay (success/partial).
        items_fetched: Total de itens no raw preservado.
        items_new: Itens criados (fontes novas).
        items_updated: Itens com conteúdo novo (novas versões de evidência).
        items_unchanged: Itens já conhecidos (idempotência).
        current_hash: Hash estável do payload re-executado.
        errors: Erros encontrados durante o replay.
    """

    run_id: str
    source: str
    replay_of: str
    status: str = "running"
    items_fetched: int = 0
    items_new: int = 0
    items_updated: int = 0
    items_unchanged: int = 0
    current_hash: str | None = None
    errors: list[str] = field(default_factory=list)

    def mark_success(self) -> None:
        """Marca o replay como bem-sucedido."""
        self.status = "success"

    def mark_partial(self, reason: str) -> None:
        """Marca o replay como parcial (alguns itens falharam)."""
        self.status = "partial"
        self.errors.append(reason)


def _flatten(payload: Any) -> Iterator[dict[str, Any]]:
    """Achata um payload (dict aninhado/lista) em itens dict, em ordem estável.

    Ex.: ``{"evidence": [{...}, {...}]}`` → cada dict; ``{"section1": [...],
    "section2": [...]}`` → os dicts de cada lista.
    """
    if isinstance(payload, dict):
        for key in sorted(payload):
            value = payload[key]
            if isinstance(value, list):
                yield from _flatten(value)
            elif isinstance(value, dict):
                yield from _flatten([value])
    elif isinstance(payload, list):
        for item in payload:
            if isinstance(item, dict):
                yield item


def _item_url(item: dict[str, Any]) -> str | None:
    """Extrai a URL canônica do item (fonte_url ou URL DOU reconstruída)."""
    url = item.get("fonte_url")
    if isinstance(url, str) and url:
        return url
    # Itens DOU do reingestion não trazem fonte_url; a URL é derivada de
    # section/date para reproduzir o mesmo comportamento da coleta original.
    section = item.get("section")
    day = item.get("date")
    if isinstance(section, int) and isinstance(day, str) and day:
        return f"https://www.in.gov.br/leitura/jornal/{day}/secao/{section}"
    return None


def _item_content(item: dict[str, Any]) -> str:
    """Extrai o conteúdo textual do item (base do fingerprint)."""
    for key in ("descricao", "text", "summary", "trecho"):
        value = item.get(key)
        if isinstance(value, str) and value:
            return value
    return ""


def _item_tipo(item: dict[str, Any]) -> str:
    """Tipo de evidência do item (DOU é ato_oficial)."""
    tipo = item.get("tipo")
    if isinstance(tipo, str) and tipo:
        return tipo
    if _item_url(item) is not None and "in.gov.br" in str(_item_url(item)):
        return "ato_oficial"
    return "outro"


def _parse_date(item: dict[str, Any]) -> str | None:
    """Data de publicação do item (string ISO ou None)."""
    value = item.get("data_publicacao", item.get("date"))
    if isinstance(value, str) and value:
        return value[:10]
    return None


async def _replay_items(
    session: AsyncSession,
    report: ReplayReport,
    items: list[dict[str, Any]],
) -> None:
    """Re-aplica persist_item para cada item com URL, contabilizando resultados."""
    for item in items:
        url = _item_url(item)
        if url is None:
            continue
        try:
            result = await persist_item(
                session,
                url=url,
                content_text=_item_content(item),
                titulo=item.get("titulo"),
                data_publicacao=_parse_date(item),
                tipo_evidencia=_item_tipo(item),
                confianca=_to_float(item.get("confianca")),
            )
            if result == "new":
                report.items_new += 1
            elif result == "updated":
                report.items_updated += 1
            else:
                report.items_unchanged += 1
        except Exception as e:
            logger.error(f"[Replay] item falhou ({url}): {e}")
            report.errors.append(f"{url}: {e!s}")


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


async def replay_run(run_id: str) -> ReplayReport:
    """Re-executa um run a partir do raw preservado (idempotente).

    Lê o payload raw do disco, re-aplica a lógica de versionamento e cria um
    novo ``IngestionRun`` (status success) com ``metadata_json.replay_of``
    apontando para o run original.

    Args:
        run_id: ID do run a re-executar.

    Returns:
        ReplayReport com o resultado.

    Raises:
        ValueError: Se o run não existir no banco.
        FileNotFoundError: Se o raw preservado não existir em disco.
    """
    async with get_session() as session:
        original = await session.get(IngestionRun, run_id)
    if original is None:
        raise ValueError(f"Run não encontrado: {run_id}")

    loaded = load_raw(original.source, run_id)
    if loaded is None:
        raise FileNotFoundError(f"Raw preservado não encontrado para o run {run_id}")
    payload, _artifact = loaded

    report = ReplayReport(
        run_id=str(uuid.uuid4()),
        source=original.source,
        replay_of=run_id,
        current_hash=stable_hash(payload),
    )
    items = list(_flatten(payload))
    report.items_fetched = len(items)

    async with get_session() as session:
        await _replay_items(session, report, items)
        await session.commit()

    report.status = "partial" if report.errors else "success"
    await _persist_replay_run(report)

    logger.info(
        f"[Replay] run {run_id} → {report.run_id}: "
        f"new={report.items_new}, updated={report.items_updated}, "
        f"unchanged={report.items_unchanged}, status={report.status}"
    )
    return report


async def _persist_replay_run(report: ReplayReport) -> None:
    """Persiste o novo run do replay com metadata de rastreabilidade."""
    now = datetime.now(UTC)
    async with get_session() as session:
        run = IngestionRun(
            id=report.run_id,
            started_at=now,
            finished_at=now,
            source=report.source,
            status=report.status,
            previous_hash=None,
            current_hash=report.current_hash,
            items_fetched=report.items_fetched,
            items_new=report.items_new,
            items_updated=report.items_updated,
            items_unchanged=report.items_unchanged,
            error_message="\n".join(report.errors) if report.errors else None,
            metadata_json={
                "replay": True,
                "replay_of": report.replay_of,
                "parser_version": None,
            },
        )
        session.add(run)
        await session.flush()
