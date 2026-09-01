"""Interface Telegram do Cognitia Brain."""

from __future__ import annotations

import asyncio
import datetime
import logging
import os
import uuid
from functools import wraps
from pathlib import Path
from typing import Any, Callable

from telegram import BotCommand, InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import (
    ApplicationBuilder,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

from cognitia_brain.config import Config
from cognitia_brain.db import VectorDB
from cognitia_brain.llm_client import LLMClient
from cognitia_brain.pipeline import ingerir_item
from cognitia_brain.scheduler import (
    are_proactive_notifications_enabled,
    daily_analysis_job,
    web_scout_job,
    weekly_digest_job,
)
from cognitia_brain.rate_limiter import rate_limited
from cognitia_brain.circuit_breaker import ollama_circuit_breaker
from cognitia_brain.conversation_memory import conversation_memory
from cognitia_brain.proativo import (
    AlertasStore,
    FocusManager,
    gerar_sintese_tema,
    inferir_foco,
    montar_alerta_conexao,
)
from cognitia_brain.graph import GraphDB

logger = logging.getLogger(__name__)


def restricted(func: Callable) -> Callable:
    """Decorador para restringir o acesso apenas ao allowed_chat_id."""
    @wraps(func)
    async def wrapped(update: Update, context: ContextTypes.DEFAULT_TYPE, *args: Any, **kwargs: Any) -> Any:
        # Pega a config injetada no context.bot_data
        config: Config = context.bot_data["config"]
        user_id = str(update.effective_user.id) if update.effective_user else ""
        
        if config.allowed_chat_id and user_id != config.allowed_chat_id:
            logger.warning(f"Acesso negado para o usuário {user_id}.")
            return
            
        return await func(update, context, *args, **kwargs)
    return wrapped


@restricted
@rate_limited
async def start_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text("🧠 Cognitia Brain online. Use /status ou envie um documento.")


@restricted
@rate_limited
async def status_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    config: Config = context.bot_data["config"]
    db: VectorDB = context.bot_data["db"]
    llm: LLMClient = context.bot_data["llm"]
    
    alive = llm.is_alive()
    active_provider = llm.get_active_provider()
    vetores = db.count()
    
    msg = (
        "📊 **Status do Brain**\n\n"
        f"🤖 LLM: {'✅ Online' if alive else '❌ Offline'} ({active_provider})\n"
        f"📚 Vetores indexados: {vetores}\n"
        f"🧠 Modelo OpenRouter: {llm.openrouter_model}\n"
        f"🧠 Modelo Ollama Cloud: {llm.ollama_cloud_model}\n"
    )
    await update.message.reply_text(msg, parse_mode="Markdown")


@restricted
@rate_limited
async def search_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not context.args:
        await update.message.reply_text("Uso: /search <sua busca>")
        return
        
    query = " ".join(context.args)
    db: VectorDB = context.bot_data["db"]
    llm: LLMClient = context.bot_data["llm"]
    
    results = db.search(query, n_results=3)
    
    if not results or not results["documents"] or not results["documents"][0]:
        await update.message.reply_text("Nenhum resultado encontrado no acervo.")
        return
        
    docs = results["documents"][0]
    
    # Sintetizar resposta com LLM baseada nos docs recuperados
    contexto = "\n\n".join([f"--- Trecho {i+1} ---\n{doc}" for i, doc in enumerate(docs)])
    prompt = (
        "Você é o assistente local Cognitia Brain.\n"
        "Com base APENAS no contexto abaixo, responda à pergunta do usuário.\n"
        "Se o contexto não tiver a resposta, diga que não sabe com base nos documentos atuais.\n\n"
        f"Contexto:\n{contexto}\n\n"
        f"Pergunta: {query}\n\n"
        "Resposta:"
    )
    
    try:
        resposta = llm.generate(prompt)
        await update.message.reply_text(resposta or "Nenhuma resposta gerada.")
    except Exception as e:
        await update.message.reply_text(f"Erro ao consultar LLM: {e}")


@restricted
async def silence_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    import json
    from pathlib import Path
    settings_path = Path(".chromadb/bot_settings.json")
    settings_path.parent.mkdir(parents=True, exist_ok=True)
    
    data = {}
    if settings_path.exists():
        try:
            data = json.loads(settings_path.read_text(encoding="utf-8"))
        except Exception:
            pass
    data["proactive_notifications"] = False
    settings_path.write_text(json.dumps(data), encoding="utf-8")
    
    await update.message.reply_text("🔇 Notificações proativas silenciadas. Não enviarei mais relatórios de digest, alertas de conexões ou scout sem que você me peça.")


@restricted
async def notify_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    import json
    from pathlib import Path
    settings_path = Path(".chromadb/bot_settings.json")
    settings_path.parent.mkdir(parents=True, exist_ok=True)
    
    data = {}
    if settings_path.exists():
        try:
            data = json.loads(settings_path.read_text(encoding="utf-8"))
        except Exception:
            pass
    data["proactive_notifications"] = True
    settings_path.write_text(json.dumps(data), encoding="utf-8")
    
    await update.message.reply_text("🔊 Notificações proativas ativadas! Você receberá o Weekly Digest, alertas do Grafo de Conhecimento e achados do Web Scout no chat.")


@restricted
@rate_limited
async def foco_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Exibe/edita o foco de pesquisa. Uso: /foco, /foco inferir, /foco add <tema>, /foco remove <tema>."""
    config: Config = context.bot_data["config"]
    db: VectorDB = context.bot_data["db"]
    llm: LLMClient = context.bot_data["llm"]
    fm = FocusManager(config)
    args = context.args or []

    if args and args[0] == "inferir":
        await update.message.reply_text("Inferindo foco a partir do acervo recente...")
        temas = await asyncio.to_thread(inferir_foco, config, db, llm)
        if not temas:
            await update.message.reply_text("Não consegui inferir temas (acervo recente vazio ou LLM indisponível).")
            return
        fm.set_foco(temas, origem="inferido")
        await update.message.reply_text(
            f"🎯 Foco inferido: {', '.join(temas)}\nCorrija com /foco add <tema> ou /foco remove <tema>."
        )
        return

    if args and args[0] == "add" and len(args) > 1:
        for tema in args[1:]:
            fm.add(tema)
        foco = fm.get_foco()
        await update.message.reply_text(f"🎯 Foco atualizado: {', '.join(foco) or '(vazio)'}")
        return

    if args and args[0] == "remove" and len(args) > 1:
        for tema in args[1:]:
            fm.remove(tema)
        foco = fm.get_foco()
        await update.message.reply_text(f"🎯 Foco atualizado: {', '.join(foco) or '(vazio)'}")
        return

    foco = fm.get_foco()
    origem = fm.get_origem()
    msg = (
        "🎯 **Foco de Pesquisa**\n\n"
        f"Origem: `{origem}`\n"
        f"Temas: {'; '.join(foco) if foco else '*(nenhum ainda)*'}\n\n"
        "Comandos:\n"
        "• /foco inferir — sugere temas do acervo recente\n"
        "• /foco add <tema> — adiciona tema\n"
        "• /foco remove <tema> — remove tema"
    )
    await update.message.reply_text(msg, parse_mode="Markdown")


@restricted
@rate_limited
async def sintese_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Gera rascunho de revisão de literatura por tema. Uso: /sintese <tema>."""
    if not context.args:
        await update.message.reply_text("Uso: /sintese <tema>")
        return
    config: Config = context.bot_data["config"]
    db: VectorDB = context.bot_data["db"]
    llm: LLMClient = context.bot_data["llm"]
    tema = " ".join(context.args)

    await update.message.reply_text(f"Gerando rascunho sobre *{tema}*... (isso pode demorar)", parse_mode="Markdown")
    try:
        destino = await asyncio.to_thread(gerar_sintese_tema, config, db, llm, tema)
    except Exception as e:
        await update.message.reply_text(f"Falha ao gerar síntese: {e}")
        return
    await update.message.reply_text(
        f"📝 Rascunho gerado em `{destino}`.\n"
        f"Veja a página /sintese no dashboard para exportar."
    )


def _montar_teclado_alerta(indice: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🔍 Investigar conexão", callback_data=f"alerta:{indice}")],
    ])


def _registrar_alerta_pendente(context: ContextTypes.DEFAULT_TYPE, entrada: dict) -> str:
    indice = uuid.uuid4().hex[:8]
    context.bot_data.setdefault("alertas_pendentes", {})[indice] = entrada
    return indice


async def _enviar_alertas_pendentes(context: ContextTypes.DEFAULT_TYPE, chat_id: str) -> None:
    """Envia o outbox de alertas (sem espera de início de sessão)."""
    if not are_proactive_notifications_enabled():
        return
    config: Config = context.bot_data["config"]
    store = AlertasStore(config)
    entradas = store.retirar_outbox()
    if not entradas:
        return
    for entrada in entradas[-3:]:
        msg = montar_alerta_conexao(entrada.get("doc_id", ""), entrada.get("conexoes", []))
        if not msg:
            continue
        indice = _registrar_alerta_pendente(context, entrada)
        try:
            await context.bot.send_message(
                chat_id=chat_id,
                text=msg,
                parse_mode="Markdown",
                reply_markup=_montar_teclado_alerta(indice),
            )
        except Exception as e:
            logger.warning(f"Falha ao enviar alerta de conexão: {e}")


@restricted
async def alerta_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Abre diálogo de investigação da conexão apontada pelo alerta (com memória)."""
    query = update.callback_query
    await query.answer()
    indice = query.data.split(":", 1)[-1]
    entrada = context.bot_data.get("alertas_pendentes", {}).pop(indice, None)
    if not entrada:
        await query.edit_message_text("Alerta expirado ou já investigado.")
        return

    config: Config = context.bot_data["config"]
    llm: LLMClient = context.bot_data["llm"]
    user_id = str(query.from_user.id)

    conexoes = entrada.get("conexoes", [])
    texto_novo = entrada.get("texto_novo", "")
    if not conexoes or not texto_novo:
        await query.edit_message_text("Sem material suficiente para investigar.")
        return

    primeira = conexoes[0]
    contexto_memoria = conversation_memory.get_context_string(user_id)
    prompt = (
        "Você é o assistente de pesquisa Cognitia Brain.\n"
        f"O usuário acabou de registrar um material novo que se conecta com o fichamento \"{primeira.get('titulo', '')}\" "
        f"(trecho: \"{primeira.get('trecho', '')}\", afinidade {primeira.get('score', 0)}).\n\n"
        "Texto do material novo (início):\n"
        f"{texto_novo[:1500]}\n\n"
        "Explique em até 4 frases, em português, POR QUE esse material se conecta ao fichamento: "
        "aponte os pontos de contato conceituais (entidades, métodos, achados) e o que isso pode acrescentar "
        "à sua investigação. Seja específico, cite termos do material. Não invente fatos fora do texto.\n"
    )
    if contexto_memoria:
        prompt += f"\nContexto da conversa recente:\n{contexto_memoria}\n"

    conversation_memory.add_message(user_id, "user", f"Investigar conexão com {primeira.get('titulo', '')}")
    try:
        explicacao = await asyncio.to_thread(llm.generate, prompt)
        explicacao = explicacao or "(LLM não retornou explicação.)"
    except Exception as e:
        explicacao = f"(LLM indisponível: {e})"
    conversation_memory.add_message(user_id, "assistant", explicacao)

    await query.edit_message_text(
        f"{montar_alerta_conexao(entrada.get('doc_id', ''), conexoes)}\n\n"
        f"🔎 **Investigação**\n\n{explicacao}",
        parse_mode="Markdown",
    )


@restricted
@rate_limited
async def handle_document(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    config: Config = context.bot_data["config"]
    db: VectorDB = context.bot_data["db"]
    llm: LLMClient = context.bot_data["llm"]

    doc = update.message.document
    nome_arquivo = doc.file_name or "doc_telegram.pdf"
    tamanho_mb = (doc.file_size or 0) / (1024 * 1024)

    if tamanho_mb > 2048:
        await update.message.reply_text(
            f"O arquivo {nome_arquivo} tem {tamanho_mb:.1f}MB, "
            "acima do limite máximo (2GB).\n\n"
            "Arquivos muito grandes podem demorar no resumo."
        )
        return

    try:
        file = await doc.get_file()
        caminho = config.acervo_dir / nome_arquivo
        await file.download_to_drive(custom_path=caminho)
    except Exception as e:
        logger.error("Falha ao baixar arquivo %s: %s", nome_arquivo, e)
        await update.message.reply_text(
            f"Não consegui baixar {nome_arquivo} do Telegram. "
            f"Erro: {e}\n\n"
            f"Tente via web: http://100.105.17.58:8080/"
        )
        return

    await update.message.reply_text("Processando documento...")

    resposta = await asyncio.to_thread(ingerir_item, config, db, llm, caminho)
    await update.message.reply_text(resposta)
    await _enviar_alertas_pendentes(context, config.allowed_chat_id)

@restricted
@rate_limited
async def handle_audio(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    config: Config = context.bot_data["config"]
    db: VectorDB = context.bot_data["db"]
    llm: LLMClient = context.bot_data["llm"]
    
    audio = update.message.audio or update.message.voice
    if not audio:
        return
        
    file = await audio.get_file()
    caminho = config.acervo_dir / f"{audio.file_id}.ogg"
    
    await file.download_to_drive(custom_path=caminho)
    await update.message.reply_text("Processando áudio (transcrevendo e resumindo)...")
    
    resposta = await asyncio.to_thread(ingerir_item, config, db, llm, caminho, True)
    await update.message.reply_text(resposta)
    await _enviar_alertas_pendentes(context, config.allowed_chat_id)

@restricted
@rate_limited
async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    config: Config = context.bot_data["config"]
    db: VectorDB = context.bot_data["db"]
    llm: LLMClient = context.bot_data["llm"]
    
    user_id = str(update.effective_user.id)
    text = update.message.text
    
    # Save user message to conversation memory
    conversation_memory.add_message(user_id, "user", text)
    
    if text.startswith("http://") or text.startswith("https://"):
        await update.message.reply_text("Processando link web...")
        resposta = await asyncio.to_thread(ingerir_item, config, db, llm, text)
        await update.message.reply_text(resposta)
        await _enviar_alertas_pendentes(context, config.allowed_chat_id)
    else:
        # Get conversation context for RAG
        conversation_context = conversation_memory.get_context_string(user_id)
        
        # Search for relevant documents
        results = db.search(text, n_results=3)
        
        if results and results["documents"] and results["documents"][0]:
            docs = results["documents"][0]
            contexto = "\n\n".join([f"--- Trecho {i+1} ---\n{doc}" for i, doc in enumerate(docs)])
            
            # Build prompt with conversation context
            prompt = (
                "Você é o assistente local Cognitia Brain.\n"
                "Com base APENAS no contexto abaixo e no histórico da conversa, responda à pergunta do usuário.\n"
                "Se o contexto não tiver a resposta, diga que não sabe com base nos documentos atuais.\n\n"
            )
            
            if conversation_context:
                prompt += f"Histórico da conversa:\n{conversation_context}\n\n"
            
            prompt += f"Contexto dos documentos:\n{contexto}\n\n"
            prompt += f"Pergunta: {text}\n\n"
            prompt += "Resposta:"
            
            try:
                resposta = llm.generate(prompt)
                await update.message.reply_text(resposta or "Nenhuma resposta gerada.")
                
                # Save assistant response to conversation memory
                conversation_memory.add_message(user_id, "assistant", resposta or "Nenhuma resposta gerada.")
            except Exception as e:
                await update.message.reply_text(f"Erro ao consultar LLM: {e}")
        else:
            # No documents found, try to answer based on conversation context
            if conversation_context:
                prompt = (
                    "Você é o assistente local Cognitia Brain.\n"
                    "Responda à pergunta do usuário com base no histórico da conversa.\n"
                    "Se não tiver informação suficiente, diga que não sabe.\n\n"
                    f"Histórico da conversa:\n{conversation_context}\n\n"
                    f"Pergunta: {text}\n\n"
                    "Resposta:"
                )
                
                try:
                    resposta = llm.generate(prompt)
                    await update.message.reply_text(resposta or "Nenhuma resposta gerada.")
                    
                    # Save assistant response to conversation memory
                    conversation_memory.add_message(user_id, "assistant", resposta or "Nenhuma resposta gerada.")
                except Exception as e:
                    await update.message.reply_text(f"Erro ao consultar LLM: {e}")
            else:
                # No context at all, save as text note
                import tempfile
                fd, path = tempfile.mkstemp(suffix=".txt", dir=config.acervo_dir)
                with os.fdopen(fd, 'w', encoding='utf-8') as f:
                    f.write(text)
                
                await update.message.reply_text("Processando anotação de texto livre...")
                resposta = ingerir_item(config, db, llm, Path(path))
                await update.message.reply_text(resposta)

def main_bot() -> None:
    logging.basicConfig(
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        level=logging.INFO
    )
    
    config = Config.load()
    token_set = bool(config.telegram_token and "COLOQUE" not in config.telegram_token)
    chat_set = bool(config.allowed_chat_id and "COLOQUE" not in config.allowed_chat_id)
    if not token_set or not chat_set:
        missing = []
        if not token_set:
            missing.append("telegram_token")
        if not chat_set:
            missing.append("allowed_chat_id")
        logger.warning("Config incompleta: %s. Preencha em config.yaml. Encerrando sem erro.", ", ".join(missing))
        return

    db = VectorDB(config)
    llm = LLMClient(config)
    
    app = (ApplicationBuilder().token(config.telegram_token)
            .connection_pool_size(16).read_timeout(30).write_timeout(30)
            .build())
    
    # Injetar dependências no bot_data
    app.bot_data["config"] = config
    app.bot_data["db"] = db
    app.bot_data["llm"] = llm
    app.bot_data["alertas_pendentes"] = {}

    async def post_init(application: Application) -> None:
        """Ao iniciar, publica o menu de comandos e despacha alertas pendentes."""
        try:
            await application.bot.set_my_commands([
                BotCommand("start", "Iniciar o assistente"),
                BotCommand("status", "Status do brain"),
                BotCommand("foco", "Ver/inferir/editar o foco de pesquisa"),
                BotCommand("sintese", "Gerar rascunho de revisão de literatura"),
                BotCommand("search", "Pesquisar no acervo"),
                BotCommand("silence", "Silenciar notificações proativas"),
                BotCommand("notify", "Reativar notificações proativas"),
            ])
        except Exception as e:
            logger.warning(f"Falha ao publicar o menu de comandos: {e}")

        chat_id = application.bot_data["config"].allowed_chat_id
        if chat_id:
            await _enviar_alertas_pendentes(application, chat_id)
    
    app.post_init = post_init
    
    app.add_handler(CommandHandler("start", start_cmd))
    app.add_handler(CommandHandler("status", status_cmd))
    app.add_handler(CommandHandler("search", search_cmd))
    app.add_handler(CommandHandler("silence", silence_cmd))
    app.add_handler(CommandHandler("notify", notify_cmd))
    app.add_handler(CommandHandler("foco", foco_cmd))
    app.add_handler(CommandHandler("sintese", sintese_cmd))
    app.add_handler(CallbackQueryHandler(alerta_callback, pattern=r"^alerta:"))
    
    app.add_handler(MessageHandler(filters.Document.ALL, handle_document))
    app.add_handler(MessageHandler(filters.AUDIO | filters.VOICE, handle_audio))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    
    # Agendamento de rotinas proativas
    jq = app.job_queue
    if jq:
        # GMT-3 equivalente em UTC:
        # 09h00 GMT-3 = 12h00 UTC
        # 06h00 GMT-3 = 09h00 UTC
        
        # Weekly digest: Domingo às 09:00 (GMT-3) = 12:00 UTC
        # apscheduler cron usa 0=Domingo, 6=Sábado (diferente do Python weekday)
        time_weekly = datetime.time(hour=12, minute=0, tzinfo=datetime.timezone.utc)
        jq.run_daily(weekly_digest_job, time=time_weekly, days=(0,))  # 0 = Domingo no apscheduler
        
        # Daily analysis: Todos os dias às 06:00 (GMT-3) = 09:00 UTC
        time_daily = datetime.time(hour=9, minute=0, tzinfo=datetime.timezone.utc)
        jq.run_daily(daily_analysis_job, time=time_daily)
        
        # Web Scout: Todos os dias às 08:00 (GMT-3) = 11:00 UTC
        time_scout = datetime.time(hour=11, minute=0, tzinfo=datetime.timezone.utc)
        jq.run_daily(web_scout_job, time=time_scout)
    
    logger.info("Iniciando o bot (polling)...")
    app.run_polling()

if __name__ == "__main__":
    main_bot()
