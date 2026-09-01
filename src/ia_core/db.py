"""
IA Brasil — Camada de dados (SQLAlchemy async + PostgreSQL)

Ponto de entrada único para a infraestrutura de banco: engine, sessão e
re-exports das camadas `src.core.settings`, `src.core.models` e
`src.core.schemas` (issue #1081). Nenhum Settings/ORM/schema é definido aqui.

Modelo de domínio conforme CONTEXT.md §4:
  Plano → Eixo → Programa → Ação → Meta → Indicador
                                   ↳ Recurso
                                   ↳ Instituição (via link)
  Evidência → Vinculação → Ação/Meta
  Avaliação → Ação
  Evento → Ação
  Fonte → Evidência

Padrao de uso:
    async with get_session() as session:
        result = await session.execute(select(Acao))
"""

from __future__ import annotations

from collections.abc import AsyncGenerator  # noqa: TC003
from contextlib import asynccontextmanager
from typing import Any

from loguru import logger
from sqlalchemy import event, text
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from src.core.models import (
    Acao,
    AcaoInstituicao,
    AuditLog,
    Avaliacao,
    Base,
    Eixo,
    EstadoVinculo,
    Evento,
    Evidencia,
    ExecucaoFinanceira,
    Fonte,
    Indicador,
    IndicadorResultado,
    IngestionRun,
    Instituicao,
    JSONColumn,
    JSONListColumn,
    MapeamentoSiafiPbia,
    Meta,
    Plano,
    Programa,
    Recurso,
    StatusAcao,
    TipoClaim,
    TipoEvento,
    TipoEvidencia,
    TipoIndicador,
    TipoMeta,
    VinculoEvidencia,
)
from src.core.schemas import (
    AcaoCreate,
    AcaoInstituicaoCreate,
    AvaliacaoCreate,
    AvaliacaoRead,
    EixoCreate,
    EixoRead,
    EventoCreate,
    EventoRead,
    EvidenciaCreate,
    EvidenciaRead,
    FonteCreate,
    FonteRead,
    IndicadorCreate,
    IndicadorRead,
    InstituicaoCreate,
    InstituicaoRead,
    MetaCreate,
    MetaRead,
    PlanoCreate,
    PlanoRead,
    ProgramaCreate,
    ProgramaRead,
    RecursoCreate,
    RecursoRead,
    VinculoCreate,
)
from src.core.settings import Settings, get_database_url, settings

__all__ = [
    "Acao",
    "AcaoCreate",
    "AcaoInstituicao",
    "AcaoInstituicaoCreate",
    "AuditLog",
    "Avaliacao",
    "AvaliacaoCreate",
    "AvaliacaoRead",
    "Base",
    "Eixo",
    "EixoCreate",
    "EixoRead",
    "EstadoVinculo",
    "Evento",
    "EventoCreate",
    "EventoRead",
    "Evidencia",
    "EvidenciaCreate",
    "EvidenciaRead",
    "ExecucaoFinanceira",
    "Fonte",
    "FonteCreate",
    "FonteRead",
    "Indicador",
    "IndicadorCreate",
    "IndicadorRead",
    "IndicadorResultado",
    "IngestionRun",
    "Instituicao",
    "InstituicaoCreate",
    "InstituicaoRead",
    "JSONColumn",
    "JSONListColumn",
    "MapeamentoSiafiPbia",
    "Meta",
    "MetaCreate",
    "MetaRead",
    "Plano",
    "PlanoCreate",
    "PlanoRead",
    "Programa",
    "ProgramaCreate",
    "ProgramaRead",
    "Recurso",
    "RecursoCreate",
    "RecursoRead",
    "Settings",
    "StatusAcao",
    "TipoClaim",
    "TipoEvento",
    "TipoEvidencia",
    "TipoIndicador",
    "TipoMeta",
    "VinculoCreate",
    "VinculoEvidencia",
    "get_database_url",
    "settings",
]

# ---------------------------------------------------------------------------
# Engine e sessão (async)
# ---------------------------------------------------------------------------

_db_url = get_database_url()
_pool_kwargs = {}
if "sqlite" not in _db_url.lower():
    _pool_kwargs = {"pool_pre_ping": True, "pool_size": 5, "max_overflow": 10}

_engine = create_async_engine(
    _db_url,
    echo=settings.database_echo,
    **_pool_kwargs,
)


# Habilita WAL mode no SQLite para evitar "database is locked" em escritas concorrentes
if "sqlite" in _db_url.lower():

    @event.listens_for(_engine.sync_engine, "connect")
    def _set_sqlite_wal(dbapi_connection: Any, connection_record: Any) -> None:
        dbapi_connection.execute("PRAGMA journal_mode=WAL")
        dbapi_connection.execute("PRAGMA busy_timeout=5000")
        dbapi_connection.execute("PRAGMA foreign_keys=ON")


_async_session: async_sessionmaker[AsyncSession] = async_sessionmaker(
    _engine, expire_on_commit=False
)


@asynccontextmanager
async def get_session() -> AsyncGenerator[AsyncSession, None]:
    """Context manager para sessão async com commit/rollback automático."""
    async with _async_session() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


async def create_tables() -> None:
    """Cria todas as tabelas (uso em testes e setup inicial; produção usa Alembic)."""
    async with _engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    logger.info("Tabelas criadas via SQLAlchemy")


async def drop_tables() -> None:
    """Remove todas as tabelas (uso exclusivo em testes)."""
    async with _engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    logger.warning("Tabelas removidas")


if __name__ == "__main__":
    import asyncio

    async def _smoke() -> None:
        await create_tables()
        async with get_session() as s:
            result = await s.execute(text("SELECT 1"))
            print("DB OK:", result.scalar())

    asyncio.run(_smoke())
