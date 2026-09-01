"""Router de autenticação — IA Brasil.

Endpoints para gerenciamento de API Keys (apenas admin) e login.
"""

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sqlalchemy.exc import IntegrityError

from src.core.db import settings
from src.core.limiter import RATE_LIMIT_AUTH, limiter
from src.modules.auth.dependencies import get_admin_api_key
from src.modules.auth.schemas import APIKeyResponse
from src.modules.auth.service import AuthService

router = APIRouter(prefix="/auth", tags=["auth"])

# Cookie httpOnly que carrega a API Key da sessão admin (lida pelo SSR do frontend)
ADMIN_SESSION_COOKIE = "ia_brasil_api_key"
ADMIN_SESSION_MAX_AGE = 60 * 60 * 8  # 8 horas


class LoginRequest(BaseModel):
    password: str


class LoginResponse(BaseModel):
    success: bool
    message: str
    api_key: str | None = None
    role: str | None = None


@router.post("/login", response_model=LoginResponse)
@limiter.limit(RATE_LIMIT_AUTH)
async def login(
    request: Request,
    body: LoginRequest,
) -> JSONResponse:
    """Login administrativo com senha mestra.

    Valida a senha contra ADMIN_PASSWORD do ambiente.
    Retorna uma API Key admin para uso nas requisições subsequentes e a
    armazena em um cookie httpOnly para que as páginas SSR do frontend
    possam autenticar as chamadas à API sem expor a chave ao JavaScript.
    """
    if not settings.admin_password:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Login não configurado. Defina ADMIN_PASSWORD no .env",
        )

    if body.password != settings.admin_password:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Senha inválida",
        )

    api_key = AuthService.create_api_key(name="session-login", role="admin")
    response = JSONResponse(
        content=LoginResponse(
            success=True,
            message="Login realizado com sucesso",
            api_key=api_key.key,
            role=api_key.role,
        ).model_dump()
    )
    response.set_cookie(
        key=ADMIN_SESSION_COOKIE,
        value=api_key.key,
        httponly=True,
        samesite="lax",
        secure=settings.app_env == "production",
        max_age=ADMIN_SESSION_MAX_AGE,
        path="/",
    )
    return response


# Constantes
KEY_PREVIEW_LENGTH = 8


@router.post("/api-keys", response_model=APIKeyResponse)
@limiter.limit(RATE_LIMIT_AUTH)
async def create_api_key(
    request: Request,
    name: str,
    role: str = "contributor",
    _current_role: str = Depends(get_admin_api_key),
) -> APIKeyResponse:
    """Cria uma nova API Key.

    Apenas usuários com role 'admin' podem criar API Keys.
    A key gerada é retornada uma única vez (na criação).
    """
    try:
        return AuthService.create_api_key(name=name, role=role)
    except IntegrityError:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Conflito: registro duplicado ou violação de restrição",
        )


@router.get("/api-keys")
@limiter.limit(RATE_LIMIT_AUTH)
async def list_api_keys(
    request: Request,
    _role: str = Depends(get_admin_api_key),
) -> list[dict[str, Any]]:
    """Lista todas as API Keys.

    Apenas usuários com role 'admin' podem listar API Keys.
    """
    keys = AuthService.list_api_keys()
    return [
        {
            "name": k.name,
            "key": k.key[:KEY_PREVIEW_LENGTH] + "..." if len(k.key) > KEY_PREVIEW_LENGTH else k.key,
            "role": k.role,
            "created_at": k.created_at.isoformat(),
            "is_active": k.is_active,
        }
        for k in keys
    ]


@router.delete("/api-keys/{key_prefix}", status_code=status.HTTP_204_NO_CONTENT)
@limiter.limit(RATE_LIMIT_AUTH)
async def deactivate_api_key(
    request: Request,
    key_prefix: str,
    _role: str = Depends(get_admin_api_key),
) -> None:
    """Desativa uma API Key.

    Apenas usuários com role 'admin' podem desativar API Keys.
    O parâmetro é o prefixo da key (primeiros 8 caracteres).
    """
    # Buscar a key completa que comece com o prefixo
    keys = AuthService.list_api_keys()
    for key in keys:
        if key.key.startswith(key_prefix):
            AuthService.deactivate_api_key(key.key)
            return

    raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail=f"API Key com prefixo {key_prefix} não encontrada",
    )
