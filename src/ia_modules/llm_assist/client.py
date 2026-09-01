"""IA Brasil — Cliente assíncrono leve para Ollama (LLM local).

Responsabilidades:
- Chamada ``POST /api/generate`` assíncrona com timeout;
- Abstention: em qualquer falha (indisponível, timeout, saída inválida)
  retorna ``None`` — nunca inventa resposta;
- Validação da saída com Pydantic (``generate_json``).

Tolerante a indisponibilidade: todas as exceções de rede/HTTP são capturadas
e convertidas em ``None`` (fallback/abstention), nunca em crash.
"""

from __future__ import annotations

import contextlib
import json
import os
import re

import httpx
from loguru import logger
from pydantic import BaseModel, ValidationError

DEFAULT_BASE_URL = "http://localhost:11434"
DEFAULT_MODEL = "llama3.2:3b-instruct-q4_K_M"
DEFAULT_TIMEOUT = 30.0

_JSON_FENCE_RE = re.compile(r"^```(?:json)?\s*|\s*```$")


class OllamaClient:
    """Cliente assíncrono leve para a API de geração do Ollama."""

    def __init__(
        self,
        base_url: str | None = None,
        model: str | None = None,
        timeout: float | None = None,
    ) -> None:
        self.base_url = (base_url or os.getenv("OLLAMA_BASE_URL") or DEFAULT_BASE_URL).rstrip("/")
        self.model = model or os.getenv("OLLAMA_DEFAULT_MODEL") or DEFAULT_MODEL
        self.timeout = timeout or float(os.getenv("OLLAMA_TIMEOUT_SECONDS") or DEFAULT_TIMEOUT)

    async def generate(self, prompt: str, system: str | None = None) -> str | None:
        """Gera texto no Ollama; ``None`` (abstention) em qualquer falha.

        Args:
            prompt: Prompt do usuário.
            system: Instruções de sistema (opcional).

        Returns:
            Texto gerado ou ``None`` se o Ollama estiver indisponível,
            demorar demais ou devolver resposta vazia/inválida.
        """
        payload: dict[str, object] = {
            "model": self.model,
            "prompt": prompt,
            "stream": False,
            "options": {"temperature": 0.0},
        }
        if system:
            payload["system"] = system
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as http:
                resp = await http.post(
                    f"{self.base_url}/api/generate",
                    json=payload,
                    headers={"Content-Type": "application/json"},
                )
            if resp.status_code != 200:
                logger.warning(f"Ollama respondeu status {resp.status_code} — abstendo")
                return None
            data = resp.json()
        except (httpx.HTTPError, ValueError) as exc:
            logger.warning(f"Ollama indisponível ou resposta inválida: {exc}")
            return None
        text = data.get("response") if isinstance(data, dict) else None
        if not isinstance(text, str) or not text.strip():
            return None
        return text.strip()

    async def generate_json[ModelT: BaseModel](
        self,
        prompt: str,
        response_model: type[ModelT],
        system: str | None = None,
    ) -> ModelT | None:
        """Gera e valida uma saída JSON com Pydantic.

        Args:
            prompt: Prompt do usuário.
            response_model: Modelo Pydantic que valida a saída.
            system: Instruções de sistema (opcional).

        Returns:
            Instância validada do modelo, ou ``None`` (abstention) se o LLM
            não responder ou a saída não passar na validação.
        """
        raw = await self.generate(prompt, system=system)
        if raw is None:
            return None
        content = _extract_json(raw)
        if content is None:
            logger.warning("Saída do LLM sem JSON válido — abstendo")
            return None
        try:
            return response_model.model_validate_json(content)
        except (ValidationError, json.JSONDecodeError) as exc:
            logger.warning(f"Saída do LLM não valida no schema {response_model.__name__}: {exc}")
            return None


def _extract_json(text: str) -> str | None:
    """Extrai o primeiro objeto JSON de uma resposta de LLM (ou ``None``).

    Aceita JSON puro, JSON dentro de fence de markdown (`````json ... `````)
    ou texto com o JSON embutido.
    """
    t = text.strip()
    if t.startswith("{"):
        return _validar_json(t)
    if t.startswith("```"):
        t = _JSON_FENCE_RE.sub("", t).strip()
        return _validar_json(t)
    inicio = t.find("{")
    fim = t.rfind("}")
    if inicio != -1 and fim > inicio:
        return _validar_json(t[inicio : fim + 1])
    return None


def _validar_json(t: str) -> str | None:
    """Retorna ``t`` se for JSON válido; senão ``None``."""
    with contextlib.suppress(json.JSONDecodeError):
        json.loads(t)
        return t
    return None


async def complete(
    prompt: str,
    system: str | None = None,
    client: OllamaClient | None = None,
) -> str | None:
    """Conveniência: gera texto usando o cliente padrão (ou injetado)."""
    llm = client or OllamaClient()
    return await llm.generate(prompt, system=system)


async def complete_json[ModelT: BaseModel](
    prompt: str,
    response_model: type[ModelT],
    system: str | None = None,
    client: OllamaClient | None = None,
) -> ModelT | None:
    """Conveniência: gera e valida JSON usando o cliente padrão (ou injetado)."""
    llm = client or OllamaClient()
    return await llm.generate_json(prompt, response_model, system=system)
