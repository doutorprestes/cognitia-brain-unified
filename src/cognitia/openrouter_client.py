"""Cliente OpenRouter para geração de conteúdo via API gratuita."""

from __future__ import annotations

import os
from typing import Optional

import requests

from cognitia_brain.config import Config


class OpenRouterClient:
    def __init__(self, config: Config) -> None:
        self.config = config
        self.api_key = os.environ.get("OPENROUTER_API_KEY", "")
        self.base_url = "https://openrouter.ai/api/v1"
        self.model = os.environ.get("OPENROUTER_MODEL", "google/gemma-4-26b-a4b-it:free")

    def is_alive(self) -> bool:
        try:
            r = requests.get(
                f"{self.base_url}/models",
                headers={"Authorization": f"Bearer {self.api_key}"},
                timeout=10,
            )
            return r.status_code == 200
        except Exception:
            return False

    def generate(self, prompt: str) -> Optional[str]:
        if not self.api_key:
            raise RuntimeError("OPENROUTER_API_KEY não configurada")

        url = f"{self.base_url}/chat/completions"
        payload = {
            "model": self.model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.3,
            "max_tokens": 1024,
        }
        try:
            r = requests.post(
                url,
                json=payload,
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                    "HTTP-Referer": "https://cognitia-brain.local",
                    "X-Title": "Cognitia Brain",
                },
                timeout=120,
            )
            r.raise_for_status()
            data = r.json()
            return (data.get("choices", [{}])[0].get("message", {}).get("content") or "").strip()
        except Exception as e:
            raise RuntimeError(f"Falha ao chamar OpenRouter: {e}") from e
