"""Cliente Ollama local para geração de fichamentos."""

from __future__ import annotations

from typing import Optional

import requests

from cognitia_brain.config import Config


class OllamaClient:
    def __init__(self, config: Config) -> None:
        self.config = config

    def is_alive(self) -> bool:
        try:
            r = requests.get(f"{self.config.ollama_base_url}/api/tags", timeout=10)
            return r.status_code == 200
        except Exception:  # noqa: BLE001
            return False

    def generate(self, prompt: str) -> Optional[str]:
        url = f"{self.config.ollama_base_url}/api/generate"
        payload = {
            "model": self.config.ollama_model,
            "prompt": prompt,
            "stream": False,
            "options": {
                "temperature": self.config.temperature,
                "num_predict": self.config.max_tokens,
            },
        }
        try:
            r = requests.post(url, json=payload, timeout=self.config.ollama_timeout)
            r.raise_for_status()
            data = r.json()
            return (data.get("response") or "").strip()
        except Exception as e:  # noqa: BLE001
            raise RuntimeError(f"Falha ao chamar Ollama: {e}") from e

    @staticmethod
    def build_resumo_prompt(titulo: str, texto: str) -> str:
        prefixo_base = (
            "Você é um assistente de pesquisa acadêmica.\n"
            "Analise o material abaixo e gere um fichamento executivo em português brasileiro:\n"
            "1) Título ou identificação do texto.\n"
            "2) Resumo em 3 a 6 linhas.\n"
            "3) Palavras-chave: 5 a 7 termos.\n"
            "4) Relevância para pesquisa: MARL, robótica coletiva, cognição distribuída, ética em IA.\n"
            "5) Conexões com outros materiais do acervo: cite apenas se houver indício claro no texto.\n"
            "Se o texto for insuficiente, diga isso explicitamente.\n\n"
        )
        trecho = texto[:4000] if len(texto) > 4000 else texto
        return f"{prefixo_base}Material:\n{trecho}\n\nFichamento Executivo:"
