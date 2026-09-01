"""IA Brasil — Assistência LLM local (Ollama) com citação obrigatória.

Extração assistida de indicadores, resumos com fonte e candidatos a
contradição. O LLM é sempre ASSISTENTE: propõe, nunca decide; abstém-se
quando indisponível ou com saída inválida (sem crash, sem dados falsos).
"""

from .client import OllamaClient, complete, complete_json
from .schemas import (
    ClaimData,
    ContradictionCandidate,
    ContradictionJudgment,
    ExtractedIndicator,
    ExtractionResult,
    SummarizationResult,
)
from .service import (
    claim_from_evidencia,
    extract_indicators,
    find_contradictions,
    summarize_evidence,
)

__all__ = [
    "ClaimData",
    "ContradictionCandidate",
    "ContradictionJudgment",
    "ExtractedIndicator",
    "ExtractionResult",
    "OllamaClient",
    "SummarizationResult",
    "claim_from_evidencia",
    "complete",
    "complete_json",
    "extract_indicators",
    "find_contradictions",
    "summarize_evidence",
]
