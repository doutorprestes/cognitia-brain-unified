"""Auth Module — IA Brasil.

Módulo de autenticação via API Key para endpoints de escrita.
Autenticação simples para permitindo escrita de evidências, vínculos e avaliações.
"""

from .dependencies import get_admin_api_key, get_api_key, get_contributor_api_key, verify_api_key
from .schemas import APIKeyCreate, APIKeyRead, APIKeyResponse
from .service import AuthService

__all__ = [
    "APIKeyCreate",
    "APIKeyRead",
    "APIKeyResponse",
    "AuthService",
    "get_admin_api_key",
    "get_api_key",
    "get_contributor_api_key",
    "verify_api_key",
]
