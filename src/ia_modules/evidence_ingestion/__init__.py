"""Evidence Ingestion Module — IA Brasil.

Módulo responsável pela ingestão manual de evidências externas.
Conforme domain-model.md: Evidência → Documento ou registro público que comprova ou refuta execução.
"""

from .schemas import (
    EvidenciaCreateExtended,
    EvidenciaListItem,
    EvidenciaListResponse,
    EvidenciaReadExtended,
    FonteCreateExtended,
    FonteReadExtended,
)
from .service import EvidenceService

__all__ = [
    "EvidenceService",
    "EvidenciaCreateExtended",
    "EvidenciaListItem",
    "EvidenciaListResponse",
    "EvidenciaReadExtended",
    "FonteCreateExtended",
    "FonteReadExtended",
]
