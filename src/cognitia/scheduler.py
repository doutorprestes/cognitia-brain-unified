"""Rotinas proativas de inteligência e background."""

from __future__ import annotations
import asyncio

import json
import logging
import datetime
import os
from typing import Any

from telegram.ext import ContextTypes

from cognitia_brain.config import Config
from cognitia_brain.db import VectorDB
from cognitia_brain.graph import GraphDB
from cognitia_brain.llm_client import LLMClient
from cognitia_brain.scout import WebScout

logger = logging.getLogger(__name__)


def are_proactive_notifications_enabled() -> bool:
    import json
    from pathlib import Path
    settings_path = Path(".chromadb/bot_settings.json")
    if settings_path.exists():
        try:
            data = json.loads(settings_path.read_text(encoding="utf-8"))
            return data.get("proactive_notifications", True)
        except Exception:
            pass
    return True


async def weekly_digest_job(context: ContextTypes.DEFAULT_TYPE) -> None:
    """Gera um relatorio conectando os conceitos da semana."""
    config: Config = context.bot_data["config"]
    db: VectorDB = context.bot_data["db"]
    chat_id = config.allowed_chat_id

    if not chat_id:
        return

    print("🔄 [Weekly Digest] Iniciando geração...", flush=True)
    logger.info("Executando Weekly Digest...")

    results = db.collection.get(
        where={"is_summary": True},
        limit=10
    )

    if not results or not results["documents"]:
        print("⚠️ [Weekly Digest] Nenhum resumo encontrado no acervo.", flush=True)
        results = db.collection.get(limit=10)
        if not results or not results["documents"]:
            print("⚠️ [Weekly Digest] Acervo vazio.", flush=True)
            return
        print(f"⚠️ [Weekly Digest] Sem summaries; usando {len(results['documents'])} docs gerais como fallback.", flush=True)
        docs = results["documents"]
    else:
        docs = results["documents"]
        print(f"🔄 [Weekly Digest] Processando {len(docs)} resumos para o digest...", flush=True)

    contexto = "\n\n".join([f"- {doc[:500]}" for doc in docs])

    prompt = (
        "Você é um assistente de pesquisa.\n"
        "Leia os textos abaixo e escreva um resumo curto em português.\n"
        "Regras:\n"
        "- Máximo 3 frases\n"
        "- Apenas pontos principais, sem explicações longas\n"
        "- Não invente informaçoes\n\n"
        f"Textos:\n{contexto}\n\n"
        "Resumo:"
    )

    GEN_TIMEOUT = 120

    async def _gerar_llm(prompt_text: str):
        import asyncio
        llm = LLMClient(config)
        return await asyncio.to_thread(llm.generate, prompt_text)

    resposta = None
    provider = None

    try:
        print("🔄 [Weekly Digest] Tentando LLM (OpenRouter/Ollama Cloud)...", flush=True)
        resposta = await asyncio.wait_for(_gerar_llm(prompt), timeout=GEN_TIMEOUT)
        provider = "llm"
        print("🔄 [Weekly Digest] Resposta obtida do LLM!", flush=True)
    except Exception as e:
        print(f"⚠️ [Weekly Digest] LLM falhou ({e}). Usando fallback simples.", flush=True)
        logger.warning(f"LLM falhou no digest: {e}")

    if resposta is None:
        resposta = (
            "_O LLM falhou; seguem os resumos recentes do acervo:_\n\n"
            + "\n\n".join([f"• {doc[:500]}" for doc in docs])
        )
        provider = "raw"

    msg = f"📊 **Weekly Digest**\n\n{resposta}"

    try:
        digests_dir = config.acervo_dir.parent / "digests"
        digests_dir.mkdir(parents=True, exist_ok=True)
        filename = f"digest_{datetime.datetime.now().strftime('%Y%m%d_%H%M')}.md"
        filepath = digests_dir / filename
        filepath.write_text(msg, encoding="utf-8")
        print(f"✅ [Weekly Digest] Salvo em: {filepath} (provider={provider})", flush=True)
        logger.info(f"Weekly digest salvo localmente em: {filepath}")
    except Exception as e:
        logger.error(f"Falha ao salvar digest localmente: {e}")

    if are_proactive_notifications_enabled():
        try:
            await context.bot.send_message(chat_id=chat_id, text=msg, parse_mode="Markdown")
        except Exception:
            try:
                await context.bot.send_message(chat_id=chat_id, text=msg)
            except Exception as e:
                logger.error(f"Falha ao enviar digest no Telegram: {e}")


async def daily_analysis_job(context: ContextTypes.DEFAULT_TYPE) -> None:
    """Extrai entidades e analisa conexoes."""
    config: Config = context.bot_data["config"]
    db: VectorDB = context.bot_data["db"]
    chat_id = config.allowed_chat_id

    if not chat_id:
        return

    logger.info("Executando Analise Diaria (Knowledge Graph)...")
    graph_db = GraphDB(config)

    results = db.collection.get(
        where={"is_summary": True},
        limit=3
    )

    if not results or not results["documents"]:
        return

    texto_combinado = "\n".join(results["documents"])

    prompt = (
        "Você é um extrator de grafos de conhecimento. "
        "Leia o texto abaixo e extraia entidades (pessoas, conceitos, tecnologias) e seus relacionamentos.\n"
        "Você DEVE retornar APENAS um objeto JSON válido, sem markdown, sem explicações.\n\n"
        "Formato esperado:\n"
        "{\n"
        '  "entidades": [{"nome": "Alan Turing", "tipo": "Pessoa"}],\n'
        '  "relacionamentos": [{"fonte": "Alan Turing", "alvo": "Computação", "tipo": "Criador"}]\n'
        "}\n\n"
        f"Texto:\n{texto_combinado}"
    )
    try:
        import asyncio
        llm = LLMClient(config)
        resposta = await asyncio.to_thread(llm.generate, prompt)
        json_str = resposta.strip()
        if json_str.startswith("```json"):
            json_str = json_str[7:]
        if json_str.startswith("```"):
            json_str = json_str[3:]
        if json_str.endswith("```"):
            json_str = json_str[:-3]
        dados = json.loads(json_str.strip())
        entidades = dados.get("entidades", [])
        relacionamentos = dados.get("relacionamentos", [])
    except Exception as e:
        logger.warning(f"LLM falhou ao extrair entidades ({e}). Usando fallback local...")
        keywords_map = {
            "marl": ("marl", "Conceito"),
            "multi-agent": ("marl", "Conceito"),
            "robótica": ("robótica", "Tecnologia"),
            "robotics": ("robótica", "Tecnologia"),
            "pbia": ("pbia", "Iniciativa"),
            "plano brasileiro de inteligência artificial": ("pbia", "Iniciativa"),
            "brasil": ("brasil", "País"),
            "ia": ("inteligência artificial", "Conceito"),
            "inteligência artificial": ("inteligência artificial", "Conceito"),
            "artificial intelligence": ("inteligência artificial", "Conceito"),
            "harvard": ("harvard", "Organização"),
            "hbs": ("hbs", "Organização"),
            "ética": ("ética", "Conceito"),
            "ethics": ("ética", "Conceito"),
            "reinforcement learning": ("aprendizado por reforço", "Conceito"),
            "aprendizado por reforço": ("aprendizado por reforço", "Conceito"),
            "distribuída": ("cognição distribuída", "Conceito"),
            "cognição distribuída": ("cognição distribuída", "Conceito"),
            "swarm": ("robótica coletiva", "Conceito"),
            "coletiva": ("robótica coletiva", "Conceito"),
            "mestrado": ("mestrado", "Conceito"),
            "feec": ("feec", "Organização"),
        }
        relations_rules = [
            ("marl", "robótica", "aplicado em"),
            ("marl", "aprendizado por reforço", "tipo de"),
            ("robótica coletiva", "robótica", "subárea de"),
            ("pbia", "inteligência artificial", "plano para"),
            ("pbia", "brasil", "localizado em"),
            ("inteligência artificial", "brasil", "estudo em"),
            ("hbs", "harvard", "parte de"),
            ("ética", "inteligência artificial", "aplicado a"),
            ("mestrado", "feec", "realizado na"),
            ("marl", "feec", "pesquisado na"),
        ]

        entidades = []
        relacionamentos = []

        docs = results.get("documents") or []
        ids = results.get("ids") or []
        for doc_text, doc_id in zip(docs, ids):
            title = doc_text.split("\n")[0].replace("# Fichamento: ", "").replace("#", "").strip() or doc_id
            text_lower = doc_text.lower()

            entidades.append({"nome": title, "tipo": "Documento"})
            detected = set()
            for kw, (name, type_) in keywords_map.items():
                if kw in text_lower:
                    entidades.append({"nome": name, "tipo": type_})
                    detected.add(name)
                    relacionamentos.append({"fonte": title, "alvo": name, "tipo": "menciona"})
            for src, tgt, rel_type in relations_rules:
                if src in detected and tgt in detected:
                    relacionamentos.append({"fonte": src, "alvo": tgt, "tipo": rel_type})

        if entidades or relacionamentos:
            intersecoes = graph_db.merge_data(entidades, relacionamentos)

            if intersecoes:
                temas = ", ".join(list(intersecoes)[:5])
                msg = (
                    "🧠 **Alerta de Insight (Grafo)**\n\n"
                    f"A análise noturna encontrou novas conexões para conceitos antigos que você estudava: *{temas}*.\n"
                    "Eles apareceram conectados com os materiais de ontem!"
                )
                if are_proactive_notifications_enabled():
                    await context.bot.send_message(chat_id=chat_id, text=msg, parse_mode="Markdown")

            logger.info(f"Grafo atualizado. {len(entidades)} entidades adicionadas.")
    except Exception as e:
        logger.error(f"Erro na extração de entidades: {e}")


async def web_scout_job(context: ContextTypes.DEFAULT_TYPE) -> None:
    """Busca ativamente por novos artigos e envia ao usuario."""
    config: Config = context.bot_data["config"]
    llm: LLMClient = context.bot_data["llm"]
    chat_id = config.allowed_chat_id

    if not chat_id:
        return

    logger.info("Executando Web Scout...")
    scout = WebScout(config)

    resultados = scout.run_scout()

    if not resultados:
        logger.info("Scout: Nenhum material novo encontrado hoje.")
        return

    for item in resultados[:3]:
        titulo = item.get("title", "Sem título")
        url = item.get("url", "")
        fonte = item.get("source", "")
        abstract = item.get("abstract", "")

        explicacao = "Sem resumo disponível."
        if abstract:
            prompt = (
                "Leia o resumo abaixo, traduza para o português e resuma a ideia central em no máximo 2 linhas.\n"
                "Seja muito direto. Não adicione saudações.\n\n"
                f"Resumo: {abstract}"
            )
            try:
                explicacao = llm.generate(prompt).strip()
            except Exception as e:
                logger.error(f"LLM falhou ao resumir scout: {e}")
                explicacao = abstract[:300] + "..."

        msg = (
            f"🔭 **Novo achado do Scout!**\n\n"
            f"*{titulo}*\n"
            f"Fonte: {fonte}\n\n"
            f"{explicacao}\n\n"
            f"Link: {url}\n\n"
            f"_(Encaminhe este link de volta para mim se quiser que eu grave na memória)_"
        )

        if are_proactive_notifications_enabled():
            try:
                await context.bot.send_message(chat_id=chat_id, text=msg, parse_mode="Markdown")
            except Exception as e:
                logger.error(f"Erro ao enviar scout no telegram: {e}")
