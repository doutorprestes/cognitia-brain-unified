"""IA Brasil — Lock distribuído para coleta de fontes.

Impede que dois workers coletem a mesma fonte simultaneamente (issue #1079):

- **PostgreSQL**: advisory lock transacional via ``pg_try_advisory_xact_lock``
  (SQLAlchemy). A sessão fica aberta durante toda a coleta e o lock é liberado
  no commit/rollback ao final do contexto.
- **SQLite (testes/fallback)**: lock em memória por processo (``asyncio.Lock``)
  com timeout — cobre concorrência intra-processo. Em SQLite não há lock entre
  processos; o log deixa isso explícito.

Uso:
    from src.collector.locking import source_lock

    async with source_lock("dou") as acquired:
        if not acquired:
            return  # outro worker está coletando
        ...  # coleta exclusiva
"""

from __future__ import annotations

import asyncio
import hashlib
from contextlib import asynccontextmanager
from typing import TYPE_CHECKING

from loguru import logger
from sqlalchemy import text as sa_text

from src.core.db import get_database_url, get_session

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator

    from sqlalchemy.ext.asyncio import AsyncSession

DEFAULT_LOCK_TIMEOUT = 300.0  # segundos aguardando o lock
_POLL_INTERVAL = 1.0  # segundos entre tentativas de pg_try_advisory_xact_lock

_process_locks: dict[str, asyncio.Lock] = {}


def _is_postgres() -> bool:
    """Retorna True quando o banco ativo é PostgreSQL."""
    return "postgresql" in get_database_url().lower()


def _lock_key(source: str) -> int:
    """Gera chave 64-bit estável (não-negativa) a partir do nome da fonte."""
    digest = hashlib.sha256(source.encode()).digest()[:8]
    return int.from_bytes(digest, byteorder="big", signed=False) & 0x7FFFFFFFFFFFFFFF


def _get_process_lock(source: str) -> asyncio.Lock:
    """Retorna o lock em memória da fonte (cria se necessário)."""
    if source not in _process_locks:
        _process_locks[source] = asyncio.Lock()
    return _process_locks[source]


async def _wait_pg_lock(
    session: AsyncSession,
    key: int,
    timeout: float,
) -> bool:
    """Polling de ``pg_try_advisory_xact_lock`` até adquirir ou esgotar timeout.

    Args:
        session: Sessão SQLAlchemy async aberta.
        key: Chave 64-bit do advisory lock.
        timeout: Tempo máximo (segundos) aguardando o lock.

    Returns:
        True se adquiriu o lock (mantido pela transação da sessão).
    """
    deadline = asyncio.get_running_loop().time() + timeout
    while True:
        result = await session.execute(
            sa_text("SELECT pg_try_advisory_xact_lock(:key)"),
            {"key": key},
        )
        if result.scalar():
            return True
        if asyncio.get_running_loop().time() >= deadline:
            return False
        await asyncio.sleep(_POLL_INTERVAL)


@asynccontextmanager
async def _pg_lock(source: str, timeout: float) -> AsyncGenerator[bool, None]:
    """Advisory lock PostgreSQL mantido durante toda a coleta."""
    try:
        async with get_session() as session:
            acquired = await _wait_pg_lock(session, _lock_key(source), timeout)
            if not acquired:
                logger.warning(
                    f"[Lock] Timeout ({timeout:.0f}s) aguardando lock de '{source}' — pulando"
                )
            yield acquired
    except Exception as e:
        logger.error(f"[Lock] Falha no advisory lock de '{source}': {e}")
        yield False


@asynccontextmanager
async def _local_lock(source: str, timeout: float) -> AsyncGenerator[bool, None]:
    """Lock em memória por processo (fallback para SQLite/testes)."""
    lock = _get_process_lock(source)
    try:
        await asyncio.wait_for(lock.acquire(), timeout=timeout)
    except TimeoutError:
        logger.warning(f"[Lock] Timeout ({timeout:.0f}s) no lock local de '{source}' — pulando")
        yield False
        return
    try:
        yield True
    finally:
        lock.release()


@asynccontextmanager
async def source_lock(
    source: str,
    timeout: float = DEFAULT_LOCK_TIMEOUT,
) -> AsyncGenerator[bool, None]:
    """Adquire o lock de exclusão mútua de uma fonte.

    Args:
        source: Nome da fonte (chave do coletor).
        timeout: Tempo máximo (segundos) aguardando o lock.

    Yields:
        True se o lock foi adquirido (a coleta pode prosseguir); False se outro
        worker detém o lock (a coleta deve ser pulada).
    """
    if _is_postgres():
        async with _pg_lock(source, timeout) as acquired:
            yield acquired
        return
    async with _local_lock(source, timeout) as acquired:
        yield acquired
