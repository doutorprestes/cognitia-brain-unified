"""Pipeline completo: descoberta → extração → resumo → persistência."""

from __future__ import annotations

from pathlib import Path
from typing import Iterable, List, Optional

from cognitia_brain.config import Config
from cognitia_brain.extract import extract_text, chunk_text
from cognitia_brain.llm_client import LLMClient
from cognitia_brain.resumo import gerar_e_salvar
from cognitia_brain.db import VectorDB
from cognitia_brain.graph import GraphDB
from cognitia_brain.proativo import avaliar_e_registrar_conexoes, registrar_ingestao


def descobrir_arquivos(cfg: Config) -> List[Path]:
    """Lista arquivos do acervo que ainda não têm fichamento em resumos/."""
    pendentes: List[Path] = []
    for ext in cfg.extensions or []:
        for p in cfg.acervo_dir.glob(f"*{ext}"):
            if not arquivo_ja_processado(cfg, p.stem):
                pendentes.append(p)
    return sorted(pendentes)


def arquivo_ja_processado(cfg: Config, nome_sem_ext: str) -> bool:
    return any(p.stem == nome_sem_ext for p in cfg.resumos_dir.glob("*.md"))


def marcar_como_processado(cfg: Config, path: Path) -> Path:
    if not cfg.move_processed:
        return path
    destino = cfg.processed_dir / f"{cfg.archive_prefix}{path.name}"
    destino.parent.mkdir(parents=True, exist_ok=True)
    destino.write_bytes(path.read_bytes())
    path.unlink()
    return destino

def clean_short_summary(text: str) -> str:
    text = text.strip()
    if text.startswith('"') and text.endswith('"'):
        text = text[1:-1]
    if text.startswith("'") and text.endswith("'"):
        text = text[1:-1]
    text = text.replace("...", "").strip()
    
    if len(text) <= 145:
        return text.rstrip(".,; ") + "."
        
    import re
    sentences = re.split(r'(?<=[.!?])\s+', text)
    accumulated = []
    current_len = 0
    for s in sentences:
        if current_len + len(s) + (1 if accumulated else 0) <= 145:
            accumulated.append(s)
            current_len += len(s) + 1
        else:
            break
            
    if accumulated:
        return " ".join(accumulated).strip()
        
    text_sliced = text[:139]
    last_space = text_sliced.rfind(" ")
    if last_space > 80:
        text_sliced = text_sliced[:last_space]
    return text_sliced.rstrip(".,; ") + "."


def ingerir_item(cfg: Config, db: VectorDB, llm: LLMClient, caminho_ou_url: str | Path, is_audio: bool = False) -> str:
    from cognitia_brain.audio import transcrever_audio
    
    if is_audio:
        texto = transcrever_audio(Path(caminho_ou_url))
        nome = Path(caminho_ou_url).stem
        tipo = "audio"
    else:
        texto = extract_text(caminho_ou_url)
        if isinstance(caminho_ou_url, str) and caminho_ou_url.startswith("http"):
            # Usar timestamp ou dominio simplificado como nome
            nome = caminho_ou_url.split("//")[-1].split("/")[0].replace(".", "_") + "_web"
            tipo = "url"
        else:
            nome = Path(caminho_ou_url).stem
            tipo = Path(caminho_ou_url).suffix

    if not texto or len(texto.strip()) < cfg.min_chars:
        return "Falha: Texto insuficiente extraído do material."
        
    try:
        alvo = gerar_e_salvar(cfg, llm, nome, texto, titulo=nome)
        chunks = chunk_text(texto)
        resumo_texto = alvo.read_text(encoding="utf-8")
        
        # Generate 140-char short summary for dashboard (complete sentence without reticence)
        prompt_short = (
            "Com base no fichamento abaixo, escreva uma única frase curta e objetiva em português (máximo 15 palavras) que resuma o texto.\n"
            "A frase DEVE ser completa, fazer sentido sozinha e terminar com ponto final.\n"
            "Não use aspas, reticências ou introduções.\n\n"
            f"Fichamento:\n{resumo_texto}"
        )
        try:
            raw_summary = llm.generate(prompt_short).strip()
            short_summary = clean_short_summary(raw_summary)
        except Exception:
            short_summary = clean_short_summary(resumo_texto)
            
        meta = {"source": str(caminho_ou_url), "type": tipo, "short_summary": short_summary}
        db.add_document(doc_id=nome, texts=chunks, metadatas=[meta] * len(chunks))
        db.add_summary(doc_id=nome, summary=resumo_texto, metadata=meta)
        registrar_ingestao(cfg, nome)
        avaliar_e_registrar_conexoes(cfg, db, GraphDB(cfg), nome, texto)
        
        # Mover se for arquivo local
        if isinstance(caminho_ou_url, Path) or (isinstance(caminho_ou_url, str) and not caminho_ou_url.startswith("http")):
            marcar_como_processado(cfg, Path(caminho_ou_url))
            
        return f"✅ Material processado!\nResumo executivo gerado e salvo em {alvo.name}.\nForam indexados {len(chunks)} trechos no banco vetorial."
    except Exception as e:
        return f"Erro ao processar material: {e}"


def executar_pipeline(cfg: Config) -> dict:
    cfg.ensure_dirs()
    arquivos = descobrir_arquivos(cfg)
    llm = LLMClient(cfg)
    db = VectorDB(cfg)
    if not llm.is_alive():
        raise RuntimeError(
            "LLM não acessível. Verifique as configurações do OpenRouter/Ollama Cloud."
        )

    resultado = {"total": len(arquivos), "ok": 0, "falha": 0, "detalhes": []}
    for caminho in arquivos:
        nome = caminho.stem
        if arquivo_ja_processado(cfg, nome):
            continue
        texto = extract_text(caminho)
        if texto is None or len(texto.strip()) < cfg.min_chars:
            resultado["detalhes"].append(
                {"arquivo": caminho.name, "status": "ignorado", "motivo": "texto insuficiente"}
            )
            marcar_como_processado(cfg, caminho)
            continue
        try:
            alvo = gerar_e_salvar(cfg, llm, nome, texto, titulo=nome)
            
            # Salvar no VectorDB
            chunks = chunk_text(texto)
            meta = {"source": caminho.name, "type": caminho.suffix}
            db.add_document(doc_id=nome, texts=chunks, metadatas=[meta] * len(chunks))
            
            resumo_texto = alvo.read_text(encoding="utf-8")
            db.add_summary(doc_id=nome, summary=resumo_texto, metadata=meta)
            registrar_ingestao(cfg, nome)
            avaliar_e_registrar_conexoes(cfg, db, GraphDB(cfg), nome, texto)
            
            marcar_como_processado(cfg, caminho)
            resultado["ok"] += 1
            resultado["detalhes"].append(
                {"arquivo": caminho.name, "status": "ok", "saida": str(alvo)}
            )
        except Exception as e:  # noqa: BLE001
            resultado["falha"] += 1
            resultado["detalhes"].append(
                {"arquivo": caminho.name, "status": "erro", "erro": str(e)}
            )
    return resultado


def diagnosticar(cfg: Config) -> dict:
    cfg.ensure_dirs()
    llm = LLMClient(cfg)
    return {
        "llm_status": "online" if llm.is_alive() else "offline",
        "active_provider": llm.get_active_provider(),
        "openrouter_model": llm.openrouter_model,
        "ollama_cloud_model": llm.ollama_cloud_model,
        "acervo": str(cfg.acervo_dir),
        "acervo_existe": cfg.acervo_dir.exists(),
        "resumos": str(cfg.resumos_dir),
        "processed": str(cfg.processed_dir),
        "extensoes": cfg.extensions,
    }
