"""Audit Module — IA Brasil.

Módulo de auditoria para registro imutável de mudanças de status.
Implementa o mecanismo de confiança central do projeto conforme CONTEXT.md §8:
"o histórico de avaliações é imutável".

Responsabilidades:
- Registrar cada mudança de status de ação de forma imutável
- Manter histórico completo e rastreável das avaliações
- Garantir integridade dos dados (sem UPDATE/DELETE)
- Fornecer consulta de histórico de auditoria

Diferença do timeline:
- AuditLog: foca em mudanças de estado de entidades (delta)
- Timeline: foca em eventos narrativos de uma ação
"""

from .pipeline import AuditDiff, AuditHistory, AuditPipeline
from .router import router
from .schemas import (
    AuditHistoryRequest,
    AuditHistoryResult,
    AuditLogCreate,
    AuditLogRead,
)
from .service import AuditService

__all__ = [
    "AuditDiff",
    "AuditHistory",
    "AuditHistoryRequest",
    "AuditHistoryResult",
    "AuditLogCreate",
    "AuditLogRead",
    "AuditPipeline",
    "AuditService",
    "router",
]
