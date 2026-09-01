"""Cliente LLM unificado com fallback: OpenRouter (primário) → Ollama Cloud (fallback)."""

from __future__ import annotations

import logging
import os
from typing import Optional

from cognitia_brain.config import Config

logger = logging.getLogger(__name__)


class LLMClient:
    """Cliente LLM que tenta OpenRouter primeiro e usa Ollama Cloud como fallback."""

    def __init__(self, config: Config) -> None:
        self.config = config
        
        # Usar configurações do Config (que já carrega do config.yaml)
        # Prioridade: variáveis de ambiente > config.yaml
        self.openrouter_api_key = os.environ.get("OPENROUTER_API_KEY", "") or config.openrouter_api_key
        self.openrouter_model = os.environ.get("OPENROUTER_MODEL", "") or config.openrouter_model
        self.openrouter_base_url = config.openrouter_base_url
        
        self.ollama_cloud_api_key = os.environ.get("OLLAMA_CLOUD_API_KEY", "") or config.ollama_cloud_api_key
        self.ollama_cloud_model = os.environ.get("OLLAMA_CLOUD_MODEL", "") or config.ollama_cloud_model
        self.ollama_cloud_base_url = config.ollama_cloud_base_url

    def is_openrouter_alive(self) -> bool:
        """Verifica se OpenRouter está disponível."""
        if not self.openrouter_api_key:
            return False
        try:
            import requests
            r = requests.get(
                f"{self.openrouter_base_url}/models",
                headers={"Authorization": f"Bearer {self.openrouter_api_key}"},
                timeout=10,
            )
            return r.status_code == 200
        except Exception:
            return False

    def is_ollama_cloud_alive(self) -> bool:
        """Verifica se Ollama Cloud está disponível."""
        if not self.ollama_cloud_api_key:
            return False
        try:
            import requests
            r = requests.get(
                f"{self.ollama_cloud_base_url}/v1/models",
                headers={"Authorization": f"Bearer {self.ollama_cloud_api_key}"},
                timeout=10,
            )
            return r.status_code == 200
        except Exception:
            return False

    def is_alive(self) -> bool:
        """Verifica se pelo menos um provedor está disponível."""
        return self.is_openrouter_alive() or self.is_ollama_cloud_alive()

    def get_active_provider(self) -> str:
        """Retorna o provedor ativo atual."""
        if self.is_openrouter_alive():
            return "openrouter"
        elif self.is_ollama_cloud_alive():
            return "ollama_cloud"
        return "none"

    def generate_openrouter(self, prompt: str) -> Optional[str]:
        """Gera texto via OpenRouter."""
        if not self.openrouter_api_key:
            raise RuntimeError("OPENROUTER_API_KEY não configurada")

        import requests
        
        url = f"{self.openrouter_base_url}/chat/completions"
        payload = {
            "model": self.openrouter_model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": self.config.temperature,
            "max_tokens": self.config.max_tokens,
        }
        
        try:
            r = requests.post(
                url,
                json=payload,
                headers={
                    "Authorization": f"Bearer {self.openrouter_api_key}",
                    "Content-Type": "application/json",
                    "HTTP-Referer": "https://cognitia-brain.local",
                    "X-Title": "Cognitia Brain",
                },
                timeout=self.config.ollama_timeout,
            )
            r.raise_for_status()
            data = r.json()
            return (data.get("choices", [{}])[0].get("message", {}).get("content") or "").strip()
        except Exception as e:
            raise RuntimeError(f"Falha ao chamar OpenRouter: {e}") from e

    def generate_ollama_cloud(self, prompt: str) -> Optional[str]:
        """Gera texto via Ollama Cloud (fallback)."""
        if not self.ollama_cloud_api_key:
            raise RuntimeError("OLLAMA_CLOUD_API_KEY não configurada")

        import requests
        
        url = f"{self.ollama_cloud_base_url}/api/generate"
        payload = {
            "model": self.ollama_cloud_model,
            "prompt": prompt,
            "stream": False,
            "options": {
                "temperature": self.config.temperature,
                "num_predict": self.config.max_tokens,
            },
        }
        
        try:
            r = requests.post(
                url,
                json=payload,
                headers={
                    "Authorization": f"Bearer {self.ollama_cloud_api_key}",
                    "Content-Type": "application/json",
                },
                timeout=self.config.ollama_timeout,
            )
            r.raise_for_status()
            data = r.json()
            return (data.get("response") or "").strip()
        except Exception as e:
            raise RuntimeError(f"Falha ao chamar Ollama Cloud: {e}") from e

    def generate(self, prompt: str) -> Optional[str]:
        """Gera texto tentando OpenRouter primeiro, depois Ollama Cloud."""
        errors = []
        
        # Tentar OpenRouter primeiro
        if self.openrouter_api_key:
            try:
                logger.info("Tentando OpenRouter...")
                result = self.generate_openrouter(prompt)
                if result:
                    logger.info("OpenRouter respondeu com sucesso")
                    return result
            except Exception as e:
                errors.append(f"OpenRouter: {e}")
                logger.warning(f"OpenRouter falhou: {e}")
        
        # Fallback para Ollama Cloud
        if self.ollama_cloud_api_key:
            try:
                logger.info("Tentando Ollama Cloud (fallback)...")
                result = self.generate_ollama_cloud(prompt)
                if result:
                    logger.info("Ollama Cloud respondeu com sucesso")
                    return result
            except Exception as e:
                errors.append(f"Ollama Cloud: {e}")
                logger.warning(f"Ollama Cloud falhou: {e}")
        
        # Se ambos falharam
        error_msg = " | ".join(errors)
        raise RuntimeError(f"Todos os provedores LLM falharam: {error_msg}")

    @staticmethod
    def build_resumo_prompt(titulo: str, texto: str) -> str:
        """Constrói prompt para fichamento."""
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
