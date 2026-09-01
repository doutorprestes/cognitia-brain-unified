"""Geração e persistência do fichamento."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Optional

from cognitia_brain.config import Config
from cognitia_brain.llm_client import LLMClient


def gerar_e_salvar(
    config: Config,
    llm: LLMClient,
    nome_base: str,
    texto: str,
    titulo: Optional[str] = None,
) -> Path:
    prompt = LLMClient.build_resumo_prompt(
        titulo or nome_base.replace("_", " ").replace("-", " ").title(),
        texto,
    )
    resposta = llm.generate(prompt)
    if not resposta:
        raise RuntimeError("LLM retornou resposta vazia.")

    destino = config.resumos_dir / f"{nome_base}.md"
    agora = datetime.now().strftime("%Y-%m-%d %H:%M")
    
    # Identificar qual provedor foi usado
    provider = llm.get_active_provider()
    model_name = llm.openrouter_model if provider == "openrouter" else llm.ollama_cloud_model
    
    conteudo = (
        f"# Fichamento: {titulo or nome_base}\n\n"
        f"Gerado em: {agora}\n\n"
        f"---\n\n"
        f"{resposta}\n\n"
        f"---\n\n"
        f"*Fichamento gerado automaticamente por Cognitia Brain "
        f"({model_name} via {provider})*\n"
    )
    destino.write_text(conteudo, encoding="utf-8")
    return destino
