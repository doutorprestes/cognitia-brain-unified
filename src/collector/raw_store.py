"""IA Brasil — Staging/raw imutável de coletas (issue #1087, D1).

Cada run de coleta preserva o conteúdo bruto (raw response/payload) em disco
em ``<RAW_DATA_DIR>/<fonte>/<run_id>/``, com checksum SHA-256. Os arquivos são
IMUTÁVEIS: nunca são sobrescritos — se o arquivo alvo já existir com o mesmo
checksum, é reutilizado (idempotência); se existir com conteúdo diferente,
um arquivo alternativo (sufixo do checksum) é criado.

O diretório raiz é configurável via env ``RAW_DATA_DIR`` (default ``data/raw``).

Uso:
    from src.collector.raw_store import save_raw, load_raw

    artifact = save_raw(source="mcti_monitor", run_id="...", payload=data)
    payload, artifact = load_raw(source="mcti_monitor", run_id="...")
"""

from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from loguru import logger

# Chaves de metadata persistidas no IngestionRun (via extra_data/metadata_json).
RAW_PATH_KEY = "raw_path"
RAW_CHECKSUM_KEY = "raw_checksum"
RAW_SIZE_KEY = "raw_size"
RAW_KIND_KEY = "raw_kind"
PARSER_VERSION_KEY = "parser_version"
QUARANTINE_REASON_KEY = "quarantine_reason"


@dataclass(frozen=True)
class RawArtifact:
    """Referência a um artefato raw preservado em disco.

    Attributes:
        path: Caminho absoluto do arquivo.
        checksum: SHA-256 do conteúdo (hex).
        size: Tamanho em bytes.
        kind: ``json`` ou ``text``.
    """

    path: str
    checksum: str
    size: int
    kind: str


def raw_data_dir() -> Path:
    """Diretório raiz do staging/raw (env ``RAW_DATA_DIR``, default ``data/raw``).

    Returns:
        Path do diretório raiz.
    """
    return Path(os.getenv("RAW_DATA_DIR", "data/raw"))


def run_dir(source: str, run_id: str) -> Path:
    """Diretório do run: ``<RAW_DATA_DIR>/<fonte>/<run_id>``.

    Args:
        source: Nome da fonte.
        run_id: ID do run.

    Returns:
        Path do diretório do run.
    """
    return raw_data_dir() / _safe_name(source) / _safe_name(run_id)


def _safe_name(value: str) -> str:
    """Sanitiza nomes de diretório (evita path traversal)."""
    return value.replace("/", "_").replace("\\", "_").replace("..", "_")


def checksum_bytes(data: bytes) -> str:
    """SHA-256 de bytes brutos.

    Args:
        data: Bytes do conteúdo.

    Returns:
        Hash SHA-256 em hexadecimal.
    """
    return hashlib.sha256(data).hexdigest()


def _serialize(payload: Any, kind: str) -> bytes:
    """Serializa o payload em bytes canônicos."""
    if kind == "text" and isinstance(payload, str):
        return payload.encode("utf-8")
    return json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        default=str,
    ).encode("utf-8")


def save_raw(
    source: str,
    run_id: str,
    payload: Any,
    *,
    kind: str = "json",
) -> RawArtifact:
    """Persiste o payload bruto de um run de forma imutável.

    Escreve em ``<RAW_DATA_DIR>/<fonte>/<run_id>/payload.json`` (ou
    ``payload.txt`` para texto puro). Nunca sobrescreve conteúdo existente:

    - se o arquivo alvo já existe com o mesmo checksum, é reutilizado;
    - se existe com checksum diferente, um arquivo alternativo
      ``payload_<checksum[:12]>.json`` é criado.

    A escrita é atômica (tmp + rename).

    Args:
        source: Nome da fonte.
        run_id: ID do run.
        payload: Conteúdo bruto (dict/list serializado como JSON ou str).
        kind: ``json`` (default) ou ``text``.

    Returns:
        RawArtifact com caminho, checksum e tamanho.
    """
    directory = run_dir(source, run_id)
    directory.mkdir(parents=True, exist_ok=True)

    data = _serialize(payload, kind)
    checksum = checksum_bytes(data)

    filename = "payload.txt" if kind == "text" else "payload.json"
    target = directory / filename
    if target.exists():
        existing_checksum = checksum_bytes(target.read_bytes())
        if existing_checksum == checksum:
            return RawArtifact(str(target), checksum, len(data), kind)
        # Conteúdo diferente já ocupou o caminho canônico → nunca sobrescreve.
        target = directory / f"payload_{checksum[:12]}.json"

    if not target.exists():
        tmp = directory / f".{target.name}.tmp"
        tmp.write_bytes(data)
        tmp.rename(target)
        logger.debug(f"[RawStore] payload preservado em {target} ({len(data)} bytes)")

    return RawArtifact(str(target), checksum, len(data), kind)


def load_raw(source: str, run_id: str) -> tuple[Any, RawArtifact] | None:
    """Carrega o payload raw preservado de um run.

    Args:
        source: Nome da fonte.
        run_id: ID do run.

    Returns:
        Tupla ``(payload, RawArtifact)`` ou None se não houver raw preservado.
    """
    directory = run_dir(source, run_id)
    candidates = ("payload.json", "payload.txt")
    for filename in candidates:
        path = directory / filename
        if not path.exists():
            continue
        raw = path.read_bytes()
        checksum = checksum_bytes(raw)
        kind = "json" if filename == "payload.json" else "text"
        artifact = RawArtifact(str(path), checksum, len(raw), kind)
        if kind == "text":
            return raw.decode("utf-8"), artifact
        try:
            return json.loads(raw.decode("utf-8")), artifact
        except json.JSONDecodeError as e:
            logger.warning(f"[RawStore] payload.json inválido em {path}: {e}")
            return None
    return None
