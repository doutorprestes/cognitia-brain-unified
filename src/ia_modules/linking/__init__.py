"""Linking Module — IA Brasil.

Módulo responsável pela vinculação explícita e rastreável entre evidências e ações/metas.
Conforme ADR-006: vinculação explícita é fundamental para transparência.
"""

from .auto_linker import auto_link, get_stats
from .classifier import RelevanceClassifier
from .embedder import Embedder
from .matcher import TextMatcher
from .schemas import LinkCreate, LinkRead, LinkSearch
from .service import LinkingService

__all__ = [
    "Embedder",
    "LinkCreate",
    "LinkRead",
    "LinkSearch",
    "LinkingService",
    "RelevanceClassifier",
    "TextMatcher",
    "auto_link",
    "get_stats",
]
