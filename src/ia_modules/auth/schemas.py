"""Schemas Pydantic para autenticação."""

from datetime import datetime

from pydantic import BaseModel, Field


class APIKeyCreate(BaseModel):
    """Schema para criação de API Key."""

    name: str = Field(..., min_length=3, max_length=100, description="Nome identificador da key")
    role: str = Field(
        default="contributor",
        description="Papéis: 'contributor' (pode criar evidências/vínculos), 'admin' (todos)",
    )


class APIKeyRead(APIKeyCreate):
    """Schema para leitura de API Key."""

    key: str = Field(..., description="Prefixo público da chave (primeiros 8 caracteres)")
    created_at: datetime = Field(..., description="Data de criação")
    expires_at: datetime | None = Field(
        default=None, description="Data de expiração (None = nunca)"
    )
    scopes: list[str] = Field(default_factory=list, description="Scopes da chave")
    is_active: bool = Field(default=True, description="Se a key está ativa")


class APIKeyResponse(BaseModel):
    """Resposta com a API Key criada (a chave em texto puro é exibida uma única vez)."""

    name: str
    key: str
    role: str
    created_at: datetime
    expires_at: datetime | None = Field(
        default=None, description="Data de expiração (None = nunca)"
    )
    scopes: list[str] = Field(default_factory=list, description="Scopes da chave")
