"""IA Brasil — Problemas HTTP no formato RFC 7807 (application/problem+json).

Helpers para construir respostas de erro padronizadas conforme a RFC 7807
(``https://www.rfc-editor.org/rfc/rfc7807``):

- ``type``: URI do tipo do problema (mais específico quando conhecido).
- ``title``: título curto e legível do problema.
- ``status``: código HTTP do problema.
- ``detail``: explicação legível específica da ocorrência.
- ``instance``: URI do recurso que originou o problema.

Os handlers globais de exceção do ``src/main.py`` usam ``problem_response``
para que erros 400/404/409/422/429/500 sejam devolvidos como
``application/problem+json`` sem quebrar os campos ``detail`` que clientes e
testes já consomem.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Final

from fastapi.responses import JSONResponse

if TYPE_CHECKING:
    from collections.abc import Mapping

    from starlette.datastructures import URL

PROBLEM_JSON_MEDIA_TYPE: Final[str] = "application/problem+json"

_BASE_TYPE_URL: Final[str] = "https://ia-brasil.org/problems"

#: URI ``type`` por código de status (RFC 7807 permite ``about:blank`` como fallback).
PROBLEM_TYPES: Final[dict[int, str]] = {
    400: f"{_BASE_TYPE_URL}/bad-request",
    404: f"{_BASE_TYPE_URL}/not-found",
    409: f"{_BASE_TYPE_URL}/conflict",
    422: f"{_BASE_TYPE_URL}/validation-error",
    429: f"{_BASE_TYPE_URL}/rate-limit-exceeded",
    500: f"{_BASE_TYPE_URL}/internal-error",
}

_DEFAULT_TITLES: Final[dict[int, str]] = {
    400: "Bad Request",
    404: "Not Found",
    409: "Conflict",
    422: "Unprocessable Entity",
    429: "Too Many Requests",
    500: "Internal Server Error",
}


def problem_type(status_code: int) -> str:
    """URI ``type`` do problema para um código de status."""
    return PROBLEM_TYPES.get(status_code, "about:blank")


def problem_title(status_code: int) -> str:
    """Título curto e legível para um código de status."""
    return _DEFAULT_TITLES.get(status_code, "Error")


def build_problem(
    *,
    status: int,
    title: str | None = None,
    detail: Any = None,
    instance: str | URL | None = None,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Constrói o corpo JSON de um problema RFC 7807.

    Args:
        status: Código HTTP do problema.
        title: Título curto; usa o título padrão do código quando omitido.
        detail: Detalhe específico da ocorrência (opcional).
        instance: URI do recurso que originou o problema (opcional).
        extra: Membros de extensão adicionais (ex.: ``code``, ``errors``).

    Returns:
        Dicionário serializável com ``type``/``title``/``status`` e campos opcionais.
    """
    body: dict[str, Any] = {
        "type": problem_type(status),
        "title": title or problem_title(status),
        "status": status,
    }
    if detail is not None:
        body["detail"] = detail
    if instance is not None:
        body["instance"] = str(instance)
    if extra:
        body.update(extra)
    return body


def problem_response(
    *,
    status: int,
    title: str | None = None,
    detail: Any = None,
    instance: str | URL | None = None,
    headers: Mapping[str, str] | None = None,
    extra: dict[str, Any] | None = None,
) -> JSONResponse:
    """Constrói uma ``JSONResponse`` com ``Content-Type: application/problem+json``.

    Args:
        status: Código HTTP do problema.
        title: Título curto; usa o título padrão do código quando omitido.
        detail: Detalhe específico da ocorrência (opcional).
        instance: URI do recurso que originou o problema (opcional).
        headers: Headers adicionais (ex.: ``Retry-After``, ``WWW-Authenticate``).
        extra: Membros de extensão adicionais (ex.: ``code``, ``errors``).

    Returns:
        ``JSONResponse`` pronta para retorno de um handler de exceção.
    """
    return JSONResponse(
        status_code=status,
        content=build_problem(
            status=status,
            title=title,
            detail=detail,
            instance=instance,
            extra=extra,
        ),
        media_type=PROBLEM_JSON_MEDIA_TYPE,
        headers=headers,
    )
