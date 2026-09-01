"""IA Brasil — PBIA Search Schemas."""

from __future__ import annotations

from pydantic import BaseModel, Field


class SearchResult(BaseModel):
    """Schema for search result."""

    id: str = Field(..., description="Ação ID")
    nome: str = Field(..., description="Nome da ação")
    descricao: str | None = Field(None, description="Descrição da ação")
    trecho_original: str | None = Field(None, description="Trecho original do PBIA")
    programa: str | None = Field(None, description="Nome do programa")
    rank: float = Field(..., description="Ranking de relevância")


class SearchResponse(BaseModel):
    """Schema for search response."""

    query: str
    total: int
    results: list[SearchResult]
