"""Módulo de monitoramento da saúde do pipeline - IA Brasil.

Endpoints:
- GET /api/v1/admin/pipeline-health - Status do pipeline SDLC
"""

from __future__ import annotations

from pydantic import BaseModel


class PipelineHealth(BaseModel):
    """Modelo de resposta para health check do pipeline."""

    runners_busy: int
    queue_length: int
    issues_open: int
    auto_generated: int
    ci_status: str
    last_dispatch: str | None = None
