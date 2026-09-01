"""Dependencies para autenticação — IA Brasil.

Dependencies do FastAPI para autenticação via API Key.

Verificação de scopes: além do papel (``role``), a dependency ``verify_api_key``
aceita ``required_scopes`` (ex.: ``["read"]``, ``["write"]``, ``["admin"]``).
Scopes padrão por papel:
- ``admin`` → ``["admin", "write", "read"]``
- ``contributor`` → ``["write", "read"]``
- outros → ``["read"]``
"""

from collections.abc import Callable
from typing import Any

from fastapi import Depends, Header, HTTPException, status

from src.modules.auth.service import AuthService

# ---------------------------------------------------------------------------
# Dependencies
# ---------------------------------------------------------------------------


async def get_api_key(
    x_api_key: str | None = Header(default=None, alias="X-API-Key"),
) -> str:
    """Extrai a API Key do header."""
    if not x_api_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="API Key não fornecida. Use o header X-API-Key.",
        )
    return x_api_key


async def verify_api_key(
    api_key: str = Depends(get_api_key),
    required_role: str | None = None,
    required_scopes: list[str] | None = None,
) -> str:
    """Verifica a API Key e retorna o role.

    Args:
        api_key: A API Key a ser verificada
        required_role: Role mínima necessária (None = qualquer role válido)
        required_scopes: Scopes exigidos (todos precisam estar presentes)

    Returns:
        O role da API Key (contributor ou admin)

    Raises:
        HTTPException: 401 se key inválida/expirada, 403 se role/scope insuficiente
    """
    record = AuthService.authenticate_api_key(api_key)

    if record is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="API Key inválida ou expirada.",
        )

    if required_role and record.role != required_role:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Role insuficiente. Requerido: {required_role}, seu role: {record.role}",
        )

    if required_scopes and not set(required_scopes).issubset(set(record.scopes)):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Scopes insuficientes. Requeridos: {required_scopes}",
        )

    return record.role


async def get_admin_api_key(api_key: str = Depends(get_api_key)) -> str:
    """Verifica que a API Key tem role de admin."""
    return await verify_api_key(api_key, required_role="admin")


async def get_admin_operator(api_key: str = Depends(get_api_key)) -> str:
    """Verifica role de admin e retorna a identidade do operador.

    A identidade é o nome da API Key autenticada (ou o prefixo público da
    chave como fallback), usada para rastrear decisões de revisão
    (revisor/aprovado_por) no workflow de revisão humana (issue #1098).

    Raises:
        HTTPException: 401 se a key for inválida/expirada, 403 se não for admin.
    """
    await verify_api_key(api_key, required_role="admin")
    record = AuthService.authenticate_api_key(api_key)
    if record is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="API Key inválida ou expirada.",
        )
    return record.name or record.key_prefix or "admin"


async def get_contributor_api_key(api_key: str = Depends(get_api_key)) -> str:
    """Verifica que a API Key tem role de contributor ou admin."""
    role = await verify_api_key(api_key)
    if role not in ("contributor", "admin"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Role contribuidor ou admin requerido.",
        )
    return role


def require_scopes(*scopes: str) -> Callable[..., Any]:
    """Factory de dependency que exige scopes específicos na API Key.

    Exemplo de uso::

        @router.get("/recurso")
        async def recurso(_role: str = Depends(require_scopes("read"))):
            ...
    """

    async def _dependency(api_key: str = Depends(get_api_key)) -> str:
        return await verify_api_key(api_key, required_scopes=list(scopes))

    return _dependency
