"""IA Brasil — Hash estável e determinístico de payloads de coleta.

Vários coletores embutem timestamps voláteis nos itens coletados
(``datetime.now().isoformat()`` em MCTI/OBIA/PowerBI, etc.), o que tornava
o hash de lote instável entre execuções (issue #1087, D2). Este módulo
normaliza o payload ANTES de hashear:

- ordena as chaves de dicts recursivamente (ordem-insensível);
- remove campos voláteis de coleta (timestamp de coleta embutido por parser);
- serializa datas de forma canônica.

O hash resultante é determinístico: duas coletas com o mesmo conteúdo
produzem o mesmo hash, mesmo que tenham ocorrido em instantes diferentes.

Uso:
    from src.collector.hashing import stable_hash, content_fingerprint

    batch_hash = stable_hash({"evidence": [{"titulo": "...", "data": now}]})
    item_hash = content_fingerprint("texto literal do item")
"""

from __future__ import annotations

import hashlib
import json
import re
from datetime import date, datetime
from typing import Any

# Chaves cujo valor costuma ser um timestamp de coleta (volátil). Quando o
# valor for um datetime ISO completo (ex.: ``datetime.now().isoformat()``),
# o par chave/valor é removido do hash — preserva conteúdo, ignora o relógio.
_VOLATILE_KEYS: frozenset[str] = frozenset(
    {
        "data",
        "timestamp",
        "checked_at",
        "collected_at",
        "coletado_em",
        "fetched_at",
        "started_at",
        "finished_at",
        "now",
    }
)

# Timestamp ISO completo (contém separador de data/hora).
_ISO_DATETIME_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}")


def is_volatile_timestamp(value: Any) -> bool:
    """True se o valor é um timestamp ISO completo (provável hora de coleta).

    Valores como ``2025-08-10T12:34:56.789+00:00`` (produzidos por
    ``datetime.now().isoformat()``) são voláteis; datas simples como
    ``2025-01-01`` não são.

    Args:
        value: Valor candidato.

    Returns:
        True se parece um timestamp de coleta volátil.
    """
    if not isinstance(value, str):
        return False
    return _ISO_DATETIME_RE.match(value) is not None


def normalize_payload(value: Any) -> Any:
    """Normaliza um payload recursivamente (ordenação + remoção de voláteis).

    Args:
        value: Payload bruto (dict, lista, primitivo).

    Returns:
        Payload normalizado, pronto para serialização canônica.
    """
    if isinstance(value, dict):
        normalized: dict[str, Any] = {}
        for key in sorted(value):
            if key in _VOLATILE_KEYS and is_volatile_timestamp(value[key]):
                # Timestamp de coleta embutido pelo parser — irrelevante para
                # o conteúdo; removido para o hash ser estável entre execuções.
                continue
            normalized[key] = normalize_payload(value[key])
        return normalized
    if isinstance(value, (list, tuple, set)):
        return [normalize_payload(item) for item in value]
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    return value


def stable_hash(payload: Any) -> str:
    """SHA-256 determinístico e estável de um payload de coleta (lote).

    Args:
        payload: Payload coletado (dict/list/primitivo).

    Returns:
        Hash SHA-256 em hexadecimal (64 chars).
    """
    normalized = normalize_payload(payload)
    content = json.dumps(normalized, sort_keys=True, default=str, ensure_ascii=False)
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def content_fingerprint(content: str) -> str:
    """SHA-256 de um conteúdo textual normalizado (fingerprint de evidência).

    Args:
        content: Conteúdo textual do item/evidência.

    Returns:
        Hash SHA-256 em hexadecimal (64 chars).
    """
    return hashlib.sha256(content.strip().encode("utf-8")).hexdigest()
