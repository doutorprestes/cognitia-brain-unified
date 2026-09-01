"""IA Brasil — Notificações de re-ingestão.

Módulo de notificações para o pipeline de re-ingestão periódica.
Suporta notificações via Telegram (webhook) e log estruturado.

Uso:
    from src.collector.notification import Notifier

    notifier = Notifier.from_env()
    await notifier.notify_ingestion(report)
"""

from __future__ import annotations

import os
from typing import Any

import httpx
from loguru import logger


class Notifier:
    """Notificador do pipeline de re-ingestão.

    Envia notificações sobre o resultado de execuções de re-ingestão
    via Telegram (webhook HTTP) e logging estruturado.

    Attributes:
        telegram_bot_token: Token do bot Telegram (opcional)
        telegram_chat_id: ID do chat de destino (opcional)
        enabled: Se notificações estão ativas
    """

    def __init__(
        self,
        telegram_bot_token: str | None = None,
        telegram_chat_id: str | None = None,
    ) -> None:
        self.telegram_bot_token = telegram_bot_token or os.getenv("TELEGRAM_BOT_TOKEN")
        self.telegram_chat_id = telegram_chat_id or os.getenv("TELEGRAM_CHAT_ID")
        self.enabled = bool(self.telegram_bot_token and self.telegram_chat_id)

    @classmethod
    def from_env(cls) -> Notifier:
        """Cria instância a partir de variáveis de ambiente.

        Returns:
            Instância do Notifier configurada
        """
        return cls()

    async def notify_ingestion(self, report: Any, *, force: bool = False) -> bool:
        """Envia notificação sobre resultado de re-ingestão.

        Args:
            report: Relatório de re-ingestão (ReingestionReport)
            force: Se True, notifica mesmo sem novos dados

        Returns:
            True se notificação foi enviada, False caso contrário
        """
        if not self.enabled:
            logger.debug("Notifications disabled — missing TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID")
            return False

        has_changes = report.items_new > 0 or report.items_updated > 0
        if not has_changes and not force:
            logger.debug("No new data — skipping notification")
            return False

        message = self._format_message(report)

        try:
            await self._send_telegram(message)
            logger.info("Notification sent successfully")
            return True
        except Exception as e:
            logger.error(f"Failed to send notification: {e}")
            return False

    async def notify_error(self, error_message: str) -> bool:
        """Envia notificação de erro no pipeline.

        Args:
            error_message: Descrição do erro

        Returns:
            True se notificação foi enviada
        """
        if not self.enabled:
            return False

        message = (
            f"❌ *IA Brasil — Erro na Re-ingestão*\n\n"
            f"Ocorreu um erro durante a execução do pipeline:\n\n"
            f"`{error_message[:500]}`"
        )

        try:
            await self._send_telegram(message)
            logger.info("Error notification sent")
            return True
        except Exception as e:
            logger.error(f"Failed to send error notification: {e}")
            return False

    async def notify_alerts(self, alerts: list[Any], *, force: bool = False) -> bool:
        """Envia notificação Telegram sobre alertas de qualidade de dados.

        Integra o módulo de data quality (issue #1096) com o notificador
        existente. Cada alerta é um objeto com ``severity``, ``category``,
        ``source`` e ``message`` (ex.: QualityAlert).

        Args:
            alerts: Lista de alertas ativos.
            force: Se True, envia mesmo com lista vazia.

        Returns:
            True se a notificação foi enviada, False caso contrário.
        """
        if not self.enabled:
            logger.debug("Notifications disabled — missing TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID")
            return False
        if not alerts and not force:
            logger.debug("No active alerts — skipping notification")
            return False

        message = self._format_alerts(alerts)

        try:
            await self._send_telegram(message)
            logger.info("Alerts notification sent successfully")
            return True
        except Exception as e:
            logger.error(f"Failed to send alerts notification: {e}")
            return False

    async def notify_tema(self, tema: str, message: str) -> bool:
        """Envia notificação Telegram para um tema de engajamento (issue #1100).

        Chamado pelo módulo de engajamento (``notify_subscribers``) após o
        filtro de opt-in por env. ``message`` já vem formatada pelo chamador.

        Args:
            tema: Chave do tema de engajamento (usada apenas no log).
            message: Mensagem formatada em Markdown.

        Returns:
            True se a notificação foi enviada, False caso contrário.
        """
        if not self.enabled:
            logger.debug("Notifications disabled — missing TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID")
            return False
        try:
            await self._send_telegram(message)
            logger.info("Tema notification sent: {}", tema)
            return True
        except Exception as e:
            logger.error(f"Failed to send tema notification: {e}")
            return False

    def _format_alerts(self, alerts: list[Any]) -> str:
        """Formata alertas de qualidade para Telegram.

        Args:
            alerts: Lista de alertas ativos (QualityAlert).

        Returns:
            Mensagem formatada em Markdown.
        """
        if not alerts:
            return "✅ *IA Brasil — Qualidade de dados*\nNenhum alerta ativo."

        lines = [f"⚠️ *IA Brasil — Qualidade de dados* ({len(alerts)} alerta(s))", ""]
        for alert in alerts[:10]:
            severity = getattr(alert, "severity", "degraded")
            source = getattr(alert, "source", None) or "geral"
            category = getattr(alert, "category", "qualidade")
            message = getattr(alert, "message", str(alert))
            emoji = "🔴" if severity == "critical" else "🟡"
            lines.append(f"{emoji} *{source}* [{category}]: {message}")

        if len(alerts) > 10:
            lines.append("")
            lines.append(f"… e mais {len(alerts) - 10} alerta(s)")

        return "\n".join(lines)

    def _format_message(self, report: Any) -> str:
        """Formata mensagem do relatório para Telegram.

        Args:
            report: Relatório de re-ingestão

        Returns:
            Mensagem formatada em Markdown
        """
        status_emoji = "✅" if report.status == "success" else "❌"
        header = f"{status_emoji} *IA Brasil — Re-ingestão*"

        lines = [
            header,
            "",
            f"*Fonte:* {report.source}",
            f"*Status:* {report.status}",
            f"*Coletados:* {report.items_fetched}",
            f"*Novos:* {report.items_new}",
            f"*Atualizados:* {report.items_updated}",
            f"*Sem mudança:* {report.items_unchanged}",
        ]

        if report.previous_hash:
            lines.append(f"*Hash anterior:* `{report.previous_hash[:12]}...`")
        if report.current_hash:
            lines.append(f"*Hash atual:* `{report.current_hash[:12]}...`")

        if report.errors:
            lines.append("")
            lines.append("*Erros:*")
            for error in report.errors[:5]:
                lines.append(f"  • `{error[:100]}`")

        return "\n".join(lines)

    async def _send_telegram(self, message: str) -> None:
        """Envia mensagem via Telegram Bot API.

        Args:
            message: Mensagem em Markdown

        Raises:
            httpx.HTTPError: Se houver erro na requisição
            ValueError: Se configuração do Telegram estiver incompleta
        """
        if not self.telegram_bot_token or not self.telegram_chat_id:
            raise ValueError("Telegram configuration incomplete")

        url = f"https://api.telegram.org/bot{self.telegram_bot_token}/sendMessage"
        max_len = 4096

        chunks = []
        start = 0
        while start < len(message):
            end = start + max_len
            if end >= len(message):
                chunks.append(message[start:])
                break
            cut = message.rfind("\n", start, end)
            if cut == -1 or cut <= start:
                cut = end
            else:
                cut += 1
            chunks.append(message[start:cut])
            start = cut

        async with httpx.AsyncClient(timeout=30) as client:
            for chunk in chunks:
                payload: dict[str, Any] = {
                    "chat_id": self.telegram_chat_id,
                    "text": chunk,
                    "parse_mode": "Markdown",
                }
                response = await client.post(url, json=payload)
                response.raise_for_status()
