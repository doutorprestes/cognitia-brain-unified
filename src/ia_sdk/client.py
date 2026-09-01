"""IA Brasil — Cliente Python mínimo para a API pública.

Cliente síncrono (``httpx``) tipado com dataclasses, cobrindo os endpoints
de leitura pública do portal IA Brasil:

- ``GET /api/v1/pbia/dashboard`` — métricas do dashboard.
- ``GET /api/v1/pbia/acoes`` — listagem de ações (page e cursor).
- ``GET /api/v1/pbia/eixos`` e ``GET /api/v1/pbia/programas`` — listagens.
- ``GET /api/v1/pbia/acoes/{id}`` — detalhe de uma ação.
- ``GET /api/v1/pbia/search`` — busca textual (FTS).

Suporte a cache: os métodos aceitam ``if_none_match`` (ETag) e expõem
``last_etag``; quando o servidor responde 304, o método retorna ``None``
para o chamador usar a representação em cache.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from typing import TYPE_CHECKING, Any

import httpx

if TYPE_CHECKING:
    from collections.abc import Iterator


class APIError(Exception):
    """Erro retornado pela API (formato RFC 7807, ``application/problem+json``)."""

    def __init__(
        self,
        status_code: int,
        title: str,
        detail: str,
        instance: str | None = None,
    ) -> None:
        """Inicializa o erro com os campos do problema RFC 7807."""
        self.status_code = status_code
        self.title = title
        self.detail = detail
        self.instance = instance
        super().__init__(f"{status_code} {title}: {detail}")


# ============================================================================
# Dataclasses de resposta
# ============================================================================


@dataclass(frozen=True)
class Acao:
    """Ação do PBIA (subset público do schema ``AcaoBase``)."""

    id: str
    programa_id: str
    nome: str
    codigo_oficial: str | None = None
    descricao: str | None = None
    status: str | None = None
    prazo: date | None = None
    pagina_doc: int | None = None


@dataclass(frozen=True)
class AcaoListPage:
    """Página da listagem de ações (page e/ou cursor)."""

    data: list[Acao]
    total: int
    page: int
    page_size: int
    pages: int
    next_cursor: str | None = None


@dataclass(frozen=True)
class Eixo:
    """Eixo do PBIA."""

    id: str
    numero: int
    nome: str
    descricao: str | None = None


@dataclass(frozen=True)
class Programa:
    """Programa do PBIA."""

    id: str
    eixo_id: str
    nome: str
    codigo: str | None = None
    descricao: str | None = None


@dataclass(frozen=True)
class Indicador:
    """Indicador do dashboard."""

    id: str
    nome: str
    tipo: str
    linha_base: float | None = None
    meta_valor: float | None = None
    unidade: str | None = None


@dataclass(frozen=True)
class Metrica:
    """Métrica calculada do dashboard."""

    id: str
    nome: str
    valor: float
    unidade: str
    descricao: str


@dataclass(frozen=True)
class StatusSummary:
    """Resumo de status de ações do dashboard."""

    status: str
    count: int
    percentage: float


@dataclass(frozen=True)
class Dashboard:
    """Resposta de ``GET /pbia/dashboard``."""

    indicadores: list[Indicador]
    metricas: list[Metrica]
    status_summary: list[StatusSummary]


# ============================================================================
# Parsing de payloads
# ============================================================================


def _parse_date(value: Any) -> date | None:
    """Converte string ISO 8601 de data em ``date`` (ou ``None``)."""
    if value is None:
        return None
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, str):
        return date.fromisoformat(value[:10])
    return None


def _parse_acao(data: dict[str, Any]) -> Acao:
    """Constrói ``Acao`` a partir do dict JSON do endpoint."""
    return Acao(
        id=str(data["id"]),
        programa_id=str(data["programa_id"]),
        nome=str(data["nome"]),
        codigo_oficial=(str(data["codigo_oficial"]) if data.get("codigo_oficial") else None),
        descricao=(str(data["descricao"]) if data.get("descricao") else None),
        status=(str(data["status"]) if data.get("status") else None),
        prazo=_parse_date(data.get("prazo")),
        pagina_doc=(int(data["pagina_doc"]) if data.get("pagina_doc") is not None else None),
    )


# ============================================================================
# Cliente
# ============================================================================


@dataclass
class IABrasilClient:
    """Cliente síncrono da API pública do IA Brasil.

    Attributes:
        base_url: Base da API (ex.: ``https://api.ia-brasil.org``).
        timeout: Timeout (segundos) de cada requisição.
        last_etag: ETag da última resposta bem-sucedida (para cache/304).
    """

    base_url: str = "https://api.ia-brasil.org"
    timeout: float = 30.0
    last_etag: str | None = field(default=None, init=False, repr=False)
    _client: httpx.Client = field(init=False, repr=False)

    def __post_init__(self) -> None:
        """Cria o ``httpx.Client`` compartilhado."""
        self._client = httpx.Client(base_url=self.base_url.rstrip("/"), timeout=self.timeout)

    def close(self) -> None:
        """Fecha o cliente HTTP subjacente."""
        self._client.close()

    def __enter__(self) -> IABrasilClient:
        """Context manager: permite ``with IABrasilClient(...) as client``."""
        return self

    def __exit__(self, *exc_info: object) -> None:
        """Fecha o cliente ao sair do bloco ``with``."""
        self.close()

    # ------------------------------------------------------------------ HTTP

    def _get(
        self,
        path: str,
        params: dict[str, Any] | None = None,
        *,
        if_none_match: str | None = None,
    ) -> tuple[bool, dict[str, Any], str | None]:
        """Executa GET tratando ETag (304) e erros RFC 7807.

        Args:
            path: Caminho relativo (ex.: ``/api/v1/pbia/acoes``).
            params: Query params da requisição.
            if_none_match: ETag da versão em cache do chamador.

        Returns:
            Tupla ``(modificado, payload, etag)``: ``modificado=False`` quando o
            servidor respondeu 304 (conteúdo não mudou) e o payload é vazio.

        Raises:
            APIError: Para qualquer resposta 4xx/5xx (corpo problem+json).
        """
        headers: dict[str, str] = {"Accept": "application/json"}
        if if_none_match:
            headers["If-None-Match"] = if_none_match
        resp = self._client.get(path, params=params, headers=headers)

        if resp.status_code == 304:
            self.last_etag = resp.headers.get("etag")
            return False, {}, self.last_etag

        if resp.status_code >= 400:
            body = self._try_json(resp)
            title = body.get("title") if isinstance(body, dict) else None
            detail = body.get("detail") if isinstance(body, dict) else None
            instance = body.get("instance") if isinstance(body, dict) else None
            raise APIError(
                status_code=resp.status_code,
                title=str(title) if title else "Error",
                detail=str(detail) if detail else resp.text,
                instance=str(instance) if instance else None,
            )

        self.last_etag = resp.headers.get("etag")
        return True, self._try_json(resp), self.last_etag

    @staticmethod
    def _try_json(resp: httpx.Response) -> dict[str, Any]:
        """Decodifica o corpo JSON da resposta (fallback para dict vazio)."""
        try:
            body = resp.json()
        except ValueError:
            return {}
        return body if isinstance(body, dict) else {}

    # ----------------------------------------------------------- Endpoints

    def get_dashboard(self, *, if_none_match: str | None = None) -> Dashboard | None:
        """Retorna as métricas do dashboard.

        Args:
            if_none_match: ETag em cache; quando não modificado, retorna ``None``.

        Returns:
            ``Dashboard`` com indicadores, métricas e resumo de status, ou
            ``None`` quando o servidor respondeu 304 (usar cache).
        """
        modified, payload, _ = self._get("/api/v1/pbia/dashboard", if_none_match=if_none_match)
        if not modified:
            return None
        return Dashboard(
            indicadores=[Indicador(**ind) for ind in payload.get("indicadores", [])],
            metricas=[Metrica(**met) for met in payload.get("metricas", [])],
            status_summary=[StatusSummary(**s) for s in payload.get("status_summary", [])],
        )

    def get_acoes(
        self,
        *,
        page: int = 1,
        page_size: int = 20,
        cursor: str | None = None,
        eixo_id: str | None = None,
        programa_id: str | None = None,
        status: str | None = None,
        if_none_match: str | None = None,
    ) -> AcaoListPage | None:
        """Lista ações do PBIA (paginação por ``page`` ou por ``cursor``).

        Args:
            page: Número da página (default 1).
            page_size: Itens por página (default 20, máx 100).
            cursor: Cursor opaco de ``next_cursor`` da página anterior.
            eixo_id: Filtro por eixo.
            programa_id: Filtro por programa.
            status: Filtro por status da ação.
            if_none_match: ETag em cache; quando não modificado, retorna ``None``.

        Returns:
            ``AcaoListPage`` com ``next_cursor`` para a próxima página, ou
            ``None`` quando o servidor respondeu 304.
        """
        params: dict[str, Any] = {"page": page, "page_size": page_size}
        if cursor is not None:
            params["cursor"] = cursor
        if eixo_id is not None:
            params["eixo_id"] = eixo_id
        if programa_id is not None:
            params["programa_id"] = programa_id
        if status is not None:
            params["status"] = status

        modified, payload, _ = self._get(
            "/api/v1/pbia/acoes", params=params, if_none_match=if_none_match
        )
        if not modified:
            return None
        return AcaoListPage(
            data=[_parse_acao(item) for item in payload.get("data", [])],
            total=int(payload.get("total", 0)),
            page=int(payload.get("page", 1)),
            page_size=int(payload.get("page_size", page_size)),
            pages=int(payload.get("pages", 0)),
            next_cursor=(str(payload["next_cursor"]) if payload.get("next_cursor") else None),
        )

    def iter_acoes(
        self,
        *,
        page_size: int = 20,
        eixo_id: str | None = None,
        programa_id: str | None = None,
        status: str | None = None,
    ) -> Iterator[Acao]:
        """Itera por todas as ações usando paginação por cursor.

        Args:
            page_size: Itens por página (default 20).
            eixo_id: Filtro por eixo.
            programa_id: Filtro por programa.
            status: Filtro por status da ação.

        Yields:
            Cada ``Acao`` de todas as páginas, até a última.
        """
        cursor: str | None = None
        while True:
            page = self.get_acoes(
                page_size=page_size,
                cursor=cursor,
                eixo_id=eixo_id,
                programa_id=programa_id,
                status=status,
            )
            if page is None:
                return
            yield from page.data
            if page.next_cursor is None:
                return
            cursor = page.next_cursor

    def get_acao(self, acao_id: str, *, if_none_match: str | None = None) -> dict[str, Any]:
        """Retorna o detalhe completo de uma ação.

        Args:
            acao_id: ID da ação.
            if_none_match: ETag em cache (304 não é tratado aqui — o detalhe
                é um payload único e o cache é responsabilidade do chamador).

        Returns:
            Dict com o payload detalhado da ação (metas, indicadores, recursos).

        Raises:
            APIError: 404 quando a ação não existe.
        """
        _, payload, _ = self._get(f"/api/v1/pbia/acoes/{acao_id}", if_none_match=if_none_match)
        return payload

    def get_eixos(self, *, page: int = 1, page_size: int = 20) -> list[Eixo]:
        """Lista os eixos do PBIA.

        Args:
            page: Número da página (default 1).
            page_size: Itens por página (default 20).

        Returns:
            Lista de ``Eixo`` da página corrente.
        """
        _, payload, _ = self._get(
            "/api/v1/pbia/eixos",
            params={"page": page, "page_size": page_size},
        )
        return [Eixo(**item) for item in payload.get("data", [])]

    def get_programas(self, *, page: int = 1, page_size: int = 20) -> list[Programa]:
        """Lista os programas do PBIA.

        Args:
            page: Número da página (default 1).
            page_size: Itens por página (default 20).

        Returns:
            Lista de ``Programa`` da página corrente.
        """
        _, payload, _ = self._get(
            "/api/v1/pbia/programas",
            params={"page": page, "page_size": page_size},
        )
        return [Programa(**item) for item in payload.get("data", [])]

    def search(self, query: str, *, limit: int = 20) -> list[dict[str, Any]]:
        """Busca textual em ações do PBIA (FTS).

        Args:
            query: Termo de busca (mínimo 2 caracteres).
            limit: Máximo de resultados (default 20, máx 100).

        Returns:
            Lista de resultados com ``id``, ``nome``, ``descricao`` e ``rank``.

        Raises:
            APIError: 422 quando a query é curta demais.
        """
        _, payload, _ = self._get(
            "/api/v1/pbia/search",
            params={"q": query, "limit": limit},
        )
        return list(payload.get("results", []))
