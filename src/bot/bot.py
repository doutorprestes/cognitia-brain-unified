"""Telegram Bot - CognitiaBrain."""
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes
from telegram.constants import ParseMode

import sys
sys.path.insert(0, '/home/jalp/Projetos/cognitia-brain-unified')

from src.shared.config import config
from src.shared.database import UnifiedDatabase

logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)


async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Comando /start."""
    welcome = (
        "🧠 <b>Bem-vindo ao CognitiaBrain!</b>\n\n"
        "Seu assistente de monitoramento acadêmico.\n\n"
        "📋 <b>Comandos disponíveis:</b>\n"
        "/status - Ver estatísticas\n"
        "/novo - Ver últimos artigos\n"
        "/pausar - Pausar notificações\n"
        "/retomar - Retomar notificações\n"
        "/ajuda - Ajuda\n\n"
        "Use o Mini App para ver os artigos:"
    )
    
    keyboard = [[InlineKeyboardButton("🧠 Abrir Mini App", web_app=config.MINI_APP_URL)]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(welcome, parse_mode=ParseMode.HTML, reply_markup=reply_markup)


async def cmd_status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Comando /status."""
    db = UnifiedDatabase()
    stats = {
        'total': db.count_items(),
        'artigos': db.count_items('artigo'),
        'grants': db.count_items('grant'),
        'feedbacks': db.count_labels()
    }
    
    text = (
        "📊 <b>Estatísticas</b>\n\n"
        f"📄 Total: {stats['total']}\n"
        f"📝 Artigos: {stats['artigos']}\n"
        f"🏛️ Grants: {stats['grants']}\n"
        f"👆 Feedbacks: {stats['feedbacks']}"
    )
    
    await update.message.reply_text(text, parse_mode=ParseMode.HTML)


async def cmd_pausar(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Comando /pausar."""
    await update.message.reply_text("⏸️ Notificações pausadas.")


async def cmd_retomar(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Comando /retomar."""
    await update.message.reply_text("▶️ Notificações retomadas!")


async def cmd_ajuda(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Comando /ajuda."""
    text = (
        "🧠 <b>CognitiaBrain</b>\n\n"
        "Monitoramento acadêmico inteligente.\n\n"
        "<b>Comandos:</b>\n"
        "/start - Início\n"
        "/status - Estatísticas\n"
        "/novo - Últimos artigos\n"
        "/pausar - Pausar notificações\n"
        "/retomar - Retomar notificações\n"
        "/ajuda - Esta mensagem\n\n"
        "💡 Use o Mini App para ver artigos e editais!"
    )
    await update.message.reply_text(text, parse_mode=ParseMode.HTML)


async def cmd_novo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Comando /novo - mostra últimos artigos."""
    db = UnifiedDatabase()
    items = db.get_unnotified()[:5]
    
    if not items:
        await update.message.reply_text("📭 Nenhum item novo.")
        return
    
    text = "📰 <b>Últimos artigos:</b>\n\n"
    for item in items:
        text += f"• {item['title'][:60]}...\n"
    
    await update.message.reply_text(text, parse_mode=ParseMode.HTML)


def main():
    """Inicia o bot."""
    application = Application.builder().token(config.TELEGRAM_BOT_TOKEN).build()
    
    application.add_handler(CommandHandler('start', cmd_start))
    application.add_handler(CommandHandler('status', cmd_status))
    application.add_handler(CommandHandler('pausar', cmd_pausar))
    application.add_handler(CommandHandler('retomar', cmd_retomar))
    application.add_handler(CommandHandler('ajuda', cmd_ajuda))
    application.add_handler(CommandHandler('novo', cmd_novo))
    
    application.run_polling()


if __name__ == '__main__':
    main()
