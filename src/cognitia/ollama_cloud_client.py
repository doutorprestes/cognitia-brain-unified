"""Cliente Ollama Cloud para geração de conteúdo via API remota."""

from __future__ import annotations

import os
from typing import Optional

import requests

from cognitia_brain.config import Config


class OllamaCloudClient:
    def __init__(self, config: Config) -> None:
        self.config = config
        self.api_key = os.environ.get("OLLAMA_CLOUD_API_KEY", "")
        self.base_url = "https://api.ollama.com"
        self.model = os.environ.get("OLLAMA_CLOUD_MODEL", "gpt-oss:120b")

    def is_alive(self) -> bool:
        try:
            r = requests.get(
                f"{self.base_url}/v1/models",
                headers={"Authorization": f"Bearer {self.api_key}"},
                timeout=10,
            )
            return r.status_code == 200
        except Exception:
            return False

    def generate(self, prompt: str) -> Optional[str]:
        if not self.api_key:
            raise RuntimeError("OLLAMA_CLOUD_API_KEY não configurada")

        url = f"{self.base_url}/api/generate"
        payload = {
            "model": self.model,
            "prompt": prompt,
            "stream": False,
            "options": {
                "temperature": 0.3,
                "num_predict": 1024,
            },
        }
        try:
            r = requests.post(
                url,
                json=payload,
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                },
                timeout=120,
            )
            r.raise_for_status()
            data = r.json()
            return (data.get("response") or "").strip()
        except Exception as e:
            raise RuntimeError(f"Falha ao chamar Ollama Cloud: {e}") from e
