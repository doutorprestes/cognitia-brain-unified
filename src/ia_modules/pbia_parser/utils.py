"""IA Brasil — PBIA Parser Utilities.

Funções utilitárias para o parser e ingestão do PBIA.
"""

from __future__ import annotations

import uuid


def generate_deterministic_id(namespace: str, *components: str) -> str:
    """Generate a deterministic ID using UUID5 hash.

    This ensures the same input always produces the same ID, preventing duplicates.

    Args:
        namespace: The namespace for the ID (e.g., 'pbia', 'inst', 'evid')
        *components: Variable components that make up the unique identifier

    Returns:
        A deterministic UUID string

    Example:
        >>> generate_deterministic_id('pbia', 'PBIA 2025', '1.0')
        '8441bd04-2b81-5ca6-8132-4806de81f702'
    """
    key = f"{namespace}:{''.join(str(c) for c in components)}"
    return str(uuid.uuid5(uuid.NAMESPACE_URL, key))
