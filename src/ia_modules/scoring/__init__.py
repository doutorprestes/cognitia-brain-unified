"""Scoring Module — IA Brasil.

Módulo responsável pelo cálculo de status das ações do PBIA.
Implementa a taxonomia definida em CONTEXT.md §10:
- Não iniciado
- Sinalizado
- Em andamento
- Parcialmente entregue
- Entregue
- Inconclusivo
- Contraditório
- Descontinuado

O status é sempre derivado de regras explícitas, nunca por inferência opaca.

Submódulos:
- rules: Regras de negócio por tipo de evidência
- pipeline: Orquestrador de scoring
- report: Gerador de relatórios de status
- service: Serviço de scoring (legado)
"""

from .pipeline import PipelineResult, PipelineRunResult, ScoringPipeline
from .report import EixoDashboard, GlobalDashboard, ScoringReport
from .rules import EvidenceInfo, RuleResult, evaluate_status
from .schemas import ScoringRequest, ScoringResult, StatusCalculation
from .service import ScoringService

__all__ = [
    "EixoDashboard",
    "EvidenceInfo",
    "GlobalDashboard",
    "PipelineResult",
    "PipelineRunResult",
    "RuleResult",
    "ScoringPipeline",
    "ScoringReport",
    "ScoringRequest",
    "ScoringResult",
    "ScoringService",
    "StatusCalculation",
    "evaluate_status",
]
