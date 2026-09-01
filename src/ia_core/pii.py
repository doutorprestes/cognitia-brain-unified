"""IA Brasil — Privacidade: redação de dados pessoais (LGPD).

Utilitários para mascarar dados pessoais (PII) em saídas públicas de
evidências, sem alterar o conteúdo armazenado no banco (redaction na saída).

Reutiliza as expressões regulares definidas em ``DataExtractor``
(``src.collector.core.extractor``) para identificar CPF, e-mail e telefone.
"""

from __future__ import annotations

import re

from loguru import logger

from src.collector.core.extractor import DataExtractor

_PATTERNS = DataExtractor().patterns

_CPF_RE = re.compile(_PATTERNS["cpf"])
_EMAIL_RE = re.compile(_PATTERNS["email"])
_PHONE_RE = re.compile(_PATTERNS["phone"])

_CPF_MASK = "***.***.***-**"
_PHONE_MASK = "(**) ****-****"


def _mask_email(match: re.Match[str]) -> str:
    """Mascara e-mail mantendo o primeiro caractere do local-part e o domínio.

    Ex.: ``admin@example.com`` -> ``a***@example.com``.

    Args:
        match: Match da regex de e-mail.

    Returns:
        E-mail mascarado.
    """
    address = match.group(0)
    local, _, domain = address.partition("@")
    if len(local) <= 1:
        return f"{local}***@{domain}"
    return f"{local[0]}***@{domain}"


def redact_pii(texto: str) -> str:
    """Remove dados pessoais (CPF, e-mail e telefone) de um texto.

    Aplica máscaras fixas:
    - CPF: ``***.***.***-**``
    - E-mail: ``a***@domínio`` (primeiro caractere + domínio preservados)
    - Telefone: ``(**) ****-****``

    Args:
        texto: Texto que pode conter dados pessoais.

    Returns:
        Texto com os dados pessoais mascarados (sem PII).
    """
    if not texto:
        return texto
    return _PHONE_RE.sub(
        _PHONE_MASK,
        _EMAIL_RE.sub(_mask_email, _CPF_RE.sub(_CPF_MASK, texto)),
    )


def log_evidence_access(evidencia_id: str, endpoint: str) -> None:
    """Registra trilha de acesso a uma evidência em saída pública.

    Registra apenas o ID da evidência, o endpoint e o timestamp (adicionado
    automaticamente pelo loguru) — **sem dados pessoais no log**.

    Args:
        evidencia_id: ID da evidência exposta.
        endpoint: Endpoint público que expôs a evidência.
    """
    logger.info(f"evidence_public_access evidencia_id={evidencia_id} endpoint={endpoint}")
