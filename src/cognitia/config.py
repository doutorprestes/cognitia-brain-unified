"""Configuração local do Cognitia Brain."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import List

import yaml


@dataclass(frozen=True)
class Config:
    # OpenRouter (primário)
    openrouter_api_key: str = ""
    openrouter_model: str = "google/gemma-4-26b-a4b-it:free"
    openrouter_base_url: str = "https://openrouter.ai/api/v1"
    openrouter_timeout: int = 120

    # Ollama Cloud (fallback)
    ollama_cloud_api_key: str = ""
    ollama_cloud_model: str = "gpt-oss:120b"
    ollama_cloud_base_url: str = "https://api.ollama.com"
    ollama_cloud_timeout: int = 120

    # Configurações do LLM
    temperature: float = 0.3
    max_tokens: int = 1024
    ollama_timeout: int = 120  # Manter compatibilidade

    acervo_dir: Path = Path("acervo")
    resumos_dir: Path = Path("resumos")
    logs_dir: Path = Path("logs")
    processed_dir: Path = Path("processed")

    # Telegram
    telegram_token: str = ""
    allowed_chat_id: str = ""

    # Scout
    scout_keywords: List[str] | None = None
    scout_rss_feeds: List[str] | None = None

    extensions: List[str] | None = None
    min_chars: int = 80
    move_processed: bool = True
    archive_prefix: str = "processed_"

    log_level: str = "INFO"

    # Manter compatibilidade com código existente
    ollama_base_url: str = "http://localhost:11434"
    ollama_model: str = "qwen2.5:3b-instruct-q4_K_M"

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "extensions",
            list(self.extensions) if self.extensions else [".txt", ".md", ".pdf", ".html"],
        )

    @classmethod
    def load(cls, path: str | Path = "config.yaml") -> Config:
        p = Path(path)
        if not p.exists():
            raise FileNotFoundError(
                f"Arquivo de configuração não encontrado: {p}. Copie config.example.yaml para config.yaml."
            )
        with p.open("r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}

        paths = data.get("paths", {})
        ingest = data.get("ingest", {})
        terminal_cfg = data.get("terminal", {})
        scout_cfg = data.get("scout", {})

        # OpenRouter
        openrouter_cfg = data.get("openrouter", {})
        
        # Ollama Cloud
        ollama_cloud_cfg = data.get("ollama_cloud", {})
        
        # LLM settings
        llm_cfg = data.get("llm", {})

        def rel(name: str, default: str) -> Path:
            v = paths.get(name, default)
            return Path(v) if v else Path(default)

        return cls(
            # OpenRouter
            openrouter_api_key=openrouter_cfg.get("api_key", cls.openrouter_api_key),
            openrouter_model=openrouter_cfg.get("model", cls.openrouter_model),
            openrouter_base_url=openrouter_cfg.get("base_url", cls.openrouter_base_url),
            openrouter_timeout=int(openrouter_cfg.get("timeout", cls.openrouter_timeout)),
            
            # Ollama Cloud
            ollama_cloud_api_key=ollama_cloud_cfg.get("api_key", cls.ollama_cloud_api_key),
            ollama_cloud_model=ollama_cloud_cfg.get("model", cls.ollama_cloud_model),
            ollama_cloud_base_url=ollama_cloud_cfg.get("base_url", cls.ollama_cloud_base_url),
            ollama_cloud_timeout=int(ollama_cloud_cfg.get("timeout", cls.ollama_cloud_timeout)),
            
            # LLM settings
            temperature=float(llm_cfg.get("temperature", cls.temperature)),
            max_tokens=int(llm_cfg.get("max_tokens", cls.max_tokens)),
            ollama_timeout=int(llm_cfg.get("timeout", cls.ollama_timeout)),
            
            acervo_dir=rel("acervo", "acervo"),
            resumos_dir=rel("resumos", "resumos"),
            logs_dir=rel("logs", "logs"),
            processed_dir=rel("processed", "processed"),
            extensions=ingest.get("extensions"),
            min_chars=int(ingest.get("min_chars", cls.min_chars)),
            move_processed=bool(ingest.get("move_processed", cls.move_processed)),
            archive_prefix=ingest.get("archive_prefix", cls.archive_prefix),
            log_level=terminal_cfg.get("log_level", cls.log_level),
            telegram_token=data.get("telegram", {}).get("token", ""),
            allowed_chat_id=str(data.get("telegram", {}).get("allowed_chat_id", "")),
            scout_keywords=scout_cfg.get("keywords", []),
            scout_rss_feeds=scout_cfg.get("rss_feeds", []),
        )

    def ensure_dirs(self) -> None:
        for d in [self.acervo_dir, self.resumos_dir, self.logs_dir, self.processed_dir]:
            Path(d).mkdir(parents=True, exist_ok=True)
