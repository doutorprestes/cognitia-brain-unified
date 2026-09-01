"""
IA Brasil — Configuração da aplicação (pydantic-settings).

Camada isolada de `src.core.models` e `src.core.schemas` para eliminar o
acoplamento reverso do antigo `src.core.db` (issue #1081): Settings não
depende de ORM nem de schemas.
"""

from __future__ import annotations

import os

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    database_url: str = "postgresql+asyncpg://ia_brasil:ia_brasil@localhost:5432/ia_brasil"
    database_echo: bool = False

    # --- App ---
    app_env: str = "development"
    public_api_url: str = "http://localhost:8000"
    allowed_origins: str = (
        "https://frontend.wine-ten-14.vercel.app,"
        "https://ia-brasil.vercel.app,"
        "https://control.tailaf9875.ts.net,"
        "http://localhost:3000,"
        "http://localhost:4321,"
        "http://localhost:8080"
    )

    admin_password: str = ""

    @property
    def allowed_origins_list(self) -> list[str]:
        """Parse comma-separated allowed_origins into a list."""
        return [o.strip() for o in self.allowed_origins.split(",") if o.strip()]


def get_database_url() -> str:
    """Retorna DATABASE_URL ou TEST_DATABASE_URL (para testes)."""
    test_url = os.getenv("TEST_DATABASE_URL")
    if test_url:
        return test_url
    return settings.database_url


settings = Settings()
# Substituir database_url se TEST_DATABASE_URL estiver definido
if test_url := os.getenv("TEST_DATABASE_URL"):
    settings.database_url = test_url
