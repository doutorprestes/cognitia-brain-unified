"""IA Brasil — Versionamento de evidência e persistência idempotente.

Quando uma re-ingestão encontra conteúdo novo para uma fonte/evidência
existente, NÃO atualizamos a evidência em lugar (o que destruiria o
histórico). Em vez disso, cada conteúdo distinto gera uma NOVA ``Evidencia``
com ID determinístico (content-addressed): ``uuid5(evid:{fonte_id}:{hash})``.

- ``Fonte`` é a identidade estável (mesma URL);
- cada versão de conteúdo vira uma ``Evidencia`` própria;
- ``Fonte.hash_conteudo`` avança para o conteúdo mais recente (a evidência
  anterior permanece no banco, vinculada à mesma fonte).

Essa abordagem usa apenas o modelo existente (sem migration): o ID
determinístico garante idempotência — re-ingestão do mesmo conteúdo resolve
para a mesma ``Evidencia`` (sem duplicar), e conteúdo novo resolve para uma
nova linha (versão nova).

Uso:
    from src.collector.versioning import persist_item

    async with get_session() as session:
        result = await persist_item(session, url=url, content_text=texto)
        # result ∈ {"new", "updated", "unchanged"}
"""

from __future__ import annotations

from datetime import date, datetime
from typing import TYPE_CHECKING, Any
from uuid import NAMESPACE_URL, uuid5

from src.collector.hashing import content_fingerprint
from src.core.db import Evidencia, Fonte, TipoEvidencia

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

# Tamanho máximo do trecho literal armazenado na evidência.
TRECHO_MAX = 2000

# Chaves canônicas aceitas para extrair o texto do item (ordem de preferência).
_CONTENT_KEYS: tuple[str, ...] = ("descricao", "text", "summary", "trecho")


def fonte_id_from_url(url: str) -> str:
    """ID determinístico da ``Fonte`` a partir da URL.

    Args:
        url: URL canônica da fonte.

    Returns:
        ID UUID5 (string).
    """
    return str(uuid5(NAMESPACE_URL, f"fonte:{url}"))


def evidencia_id(fonte_id: str, fingerprint: str) -> str:
    """ID determinístico da ``Evidencia`` (content-addressed).

    Conteúdo novo ⇒ fingerprint novo ⇒ nova ``Evidencia`` (nova versão).
    Conteúdo igual ⇒ mesmo ID ⇒ re-ingestão/replay não duplica.

    Args:
        fonte_id: ID da fonte.
        fingerprint: SHA-256 do conteúdo textual.

    Returns:
        ID UUID5 (string).
    """
    return str(uuid5(NAMESPACE_URL, f"evid:{fonte_id}:{fingerprint}"))


def _resolve_tipo(tipo: str | None) -> TipoEvidencia:
    """Resolve string de tipo para o enum ``TipoEvidencia`` (default ``outro``)."""
    if tipo is None:
        return TipoEvidencia.outro
    for member in TipoEvidencia:
        if member.value == tipo:
            return member
    return TipoEvidencia.outro


def _parse_date(value: Any) -> date | None:
    """Converte valor arbitrário em ``date`` (tolera datetime e strings)."""
    if isinstance(value, date):  # ``datetime`` é subclasse de ``date``
        return value.date() if isinstance(value, datetime) else value
    if isinstance(value, str):
        try:
            return date.fromisoformat(value[:10])
        except ValueError:
            return None
    return None


async def _add_evidencia(
    session: AsyncSession,
    *,
    fonte_id: str,
    evidencia_id_: str,
    tipo_evidencia: str,
    content_text: str,
    titulo: str | None,
    data_publicacao: date | None,
    confianca: float | None,
) -> None:
    """Cria a evidência se ainda não existir (idempotente)."""
    existing = await session.get(Evidencia, evidencia_id_)
    if existing is not None:
        return
    session.add(
        Evidencia(
            id=evidencia_id_,
            fonte_id=fonte_id,
            tipo=_resolve_tipo(tipo_evidencia),
            trecho=(content_text[:TRECHO_MAX] if content_text else None),
            resumo=titulo,
            data_evidencia=data_publicacao,
            confianca=confianca,
        )
    )
    await session.flush()


async def persist_item(
    session: AsyncSession,
    *,
    url: str,
    content_text: str,
    titulo: str | None = None,
    instituicao_emissora: str | None = None,
    tipo_documental: str | None = None,
    data_publicacao: date | str | None = None,
    tipo_evidencia: str = "outro",
    confianca: float | None = None,
) -> str:
    """Upsert de fonte/evidência com versionamento (issue #1087, D3/D5).

    Retorna ``new`` (fonte criada), ``updated`` (conteúdo novo ⇒ nova
    versão de evidência) ou ``unchanged`` (conteúdo já conhecido).

    Args:
        session: Sessão async do SQLAlchemy.
        url: URL canônica da fonte.
        content_text: Conteúdo textual do item (base do fingerprint).
        titulo: Título do item/fonte.
        instituicao_emissora: Órgão emissor.
        tipo_documental: Tipo documental (ex.: ``ato_oficial``).
        data_publicacao: Data de publicação (date ou string ISO).
        tipo_evidencia: Tipo de evidência (valor de ``TipoEvidencia``).
        confianca: Confiança 0.0-1.0.

    Returns:
        ``new`` | ``updated`` | ``unchanged``.
    """
    data_pub = _parse_date(data_publicacao)
    fingerprint = content_fingerprint(content_text)
    fonte_id = fonte_id_from_url(url)
    evidencia_id_ = evidencia_id(fonte_id, fingerprint)

    fonte = await session.get(Fonte, fonte_id)

    if fonte is None:
        session.add(
            Fonte(
                id=fonte_id,
                url=url,
                titulo=titulo,
                instituicao_emissora=instituicao_emissora,
                tipo_documental=tipo_documental,
                data_publicacao=data_pub,
                data_coleta=date.today(),
                hash_conteudo=fingerprint,
            )
        )
        await session.flush()
        await _add_evidencia(
            session,
            fonte_id=fonte_id,
            evidencia_id_=evidencia_id_,
            tipo_evidencia=tipo_evidencia,
            content_text=content_text,
            titulo=titulo,
            data_publicacao=data_pub,
            confianca=confianca,
        )
        return "new"

    if fonte.hash_conteudo == fingerprint:
        return "unchanged"

    # Conteúdo novo: cria NOVA evidência (versão nova); a evidência anterior
    # é preservada no banco. Apenas o ponteiro da fonte avança.
    fonte.hash_conteudo = fingerprint
    fonte.data_coleta = date.today()
    await _add_evidencia(
        session,
        fonte_id=fonte_id,
        evidencia_id_=evidencia_id_,
        tipo_evidencia=tipo_evidencia,
        content_text=content_text,
        titulo=titulo,
        data_publicacao=data_pub,
        confianca=confianca,
    )
    return "updated"
