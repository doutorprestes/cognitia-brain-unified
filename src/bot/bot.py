"""Unified Telegram bot."""
import logging
from typing import Optional

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes

from ..shared.config import config
from ..shared.database import UnifiedDatabase
from ..shared.metrics import GrantWatchMetrics

logger = logging.getLogger(__name__)

class CognitiaBot:
    def __init__(self, token: str, chat_id: str, db_path: Optional[str] = None):
        self.token = token
        self.chat_id = chat_id
        self.db = UnifiedDatabase(db_path)
        self.metrics = GrantWatchMetrics(self.db)
        self._app = None
        self._pausado = False

    async def iniciar(self):
        self._app = Application.builder().token(self.token).build()
        self._app.add_handler(CommandHandler('start', self._cmd_start))
        self._app.add_handler(CommandHandler('status', self._cmd_status))
        self._app.add_handler(CommandHandler('pause', self._cmd_pause))
        self._app.add_handler(CommandHandler('resume', self._cmd_resume))
        self._app.add_handler(CommandHandler('help', self._cmd_help))
        self._app.add_handler(CommandHandler('metrics', self._cmd_metrics))
        self._app.add_handler(CallbackQueryHandler(self._callback_handler))
        await self._app.run_polling()

    async def parar(self):
        if self._app:
            await self._app.stop()

    async def notificar_item(self, edital: dict):
        if self._pausado or not self._app:
            return
        item_hash = edital.get('hash', '')
        texto = f"📢 <b>NOVO {edital.get('type', 'ITEM').upper()}</b>\n\n📌 {edital.get('title', 'Sem título')}\n🏛️ Fonte: {edital.get('source', 'Desconhecida')}\n"
        if edital.get('snippet'):
            texto += f"📝 {edital['snippet'][:150]}...\n"
        if edital.get('url'):
            texto += f"🔗 <a href=\"{edital['url']}\">Acessar</a>\n"
        if edital.get('confidence'):
            texto += f"\n🎯 Confiança: {edital['confidence']*100:.0f}%"
        keyboard = [[InlineKeyboardButton('👍 Útil', callback_data=f'feedback:{item_hash}:1'), InlineKeyboardButton('👎 Não útil', callback_data=f'feedback:{item_hash}:0')]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await self._app.bot.send_message(chat_id=self.chat_id, text=texto, reply_markup=reply_markup, parse_mode='HTML', disable_web_page_preview=True)

    async def _cmd_start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        await update.message.reply_text('👋 <b>Bem-vindo ao CognitiaBrain!</b>\n\nUse /status para ver estatísticas.', parse_mode='HTML')

    async def _cmd_status(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        relatorio = self.metrics.formatar_relatorio()
        await update.message.reply_text(relatorio, parse_mode='HTML')

    async def _cmd_pause(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        self._pausado = True
        await update.message.reply_text('⏸️ Notificações pausadas.')

    async def _cmd_resume(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        self._pausado = False
        await update.message.reply_text('▶️ Notificações retomadas!')

    async def _cmd_help(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        await update.message.reply_text('<b>CognitiaBrain</b>\n\n/start\n/status\n/pause\n/resume\n/metrics\n/help', parse_mode='HTML')

    async def _cmd_metrics(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        labels = self.db.count_labels()
        await update.message.reply_text(f'📊 <b>Métricas</b>\n\nTotal feedbacks: {labels}', parse_mode='HTML')

    async def _callback_handler(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        query = update.callback_query
        await query.answer()
        data = query.data
        if not data.startswith('feedback:'):
            return
        partes = data.split(':')
        if len(partes) != 3:
            return
        _, item_hash, label_str = partes
        label = int(label_str)
        self.db.save_feedback(item_hash, label, 0.0)
        emoji = '👍' if label == 1 else '👎'
        await query.edit_message_text(text=f'{query.message.text}\n\n✅ Feedback registrado: {emoji}', parse_mode='HTML')
