import axios from "axios";
import { createLogger } from "./logger.js";
import { Opportunity } from "../types.js";

const logger = createLogger("notifications");

function formatType(type?: string): string {
  if (type === "bolsa-pessoal") return "Bolsa Pessoal";
  if (type === "grant-projeto") return "Grant de Projeto";
  return "A definir";
}

function escapeTelegramMd(text: string): string {
  return text.replace(/[_*[\]()~`>#+=|{}.!-]/g, (char) => `\\${char}`);
}

export async function sendTelegramAlert(opportunity: Opportunity): Promise<void> {
  const token = process.env.TELEGRAM_BOT_TOKEN;
  const chatId = process.env.TELEGRAM_CHAT_ID;

  if (!token || !chatId) {
    logger.warn("Telegram credentials not found, skipping alert");
    return;
  }

  const ai = opportunity.ai_analysis;
  const type = formatType(ai?.type);
  const amount = escapeTelegramMd(ai?.funding_amount || opportunity.funding_amount || "A definir no edital");
  const summary = escapeTelegramMd((ai?.executive_summary || opportunity.snippet || "").substring(0, 140));
  const eligibility = (ai?.eligibility_criteria || []).slice(0, 3);
  const keywords = (ai?.keywords || []).slice(0, 5);
  const title = escapeTelegramMd(opportunity.title);

  const message = `🚨 *NOVA OPORTUNIDADE ALTA PRIORIDADE* 🚨

*Título:* ${title}
*Fonte:* ${opportunity.source} | *Trilha:* ${opportunity.track}
*Score:* ${opportunity.score}/100 | *Prazo:* ${opportunity.date || "Não informado"}

*Tipo:* ${type}
*Valor:* ${amount}

*Resumo:*
${summary}

*Elegibilidade:*
${eligibility.map(c => `• ${escapeTelegramMd(c)}`).join("\n")}

*Keywords:* ${keywords.map(k => escapeTelegramMd(k)).join(", ")}

🔗 [Ver Edital Oficial](${opportunity.link})`;

  try {
    await axios.post(`https://api.telegram.org/bot${token}/sendMessage`, {
      chat_id: chatId,
      text: message,
      parse_mode: "Markdown"
    });
    logger.info({ title: opportunity.title }, "Telegram alert sent");
  } catch (error: any) {
    logger.error({ error: error.message }, "Failed to send Telegram alert");
  }
}

export async function sendStatusUpdate(text: string): Promise<void> {
  const token = process.env.TELEGRAM_BOT_TOKEN;
  const chatId = process.env.TELEGRAM_CHAT_ID;

  if (!token || !chatId) return;

  try {
    await axios.post(`https://api.telegram.org/bot${token}/sendMessage`, {
      chat_id: chatId,
      text: `🤖 *GrantWatch Status:* ${text}`,
      parse_mode: "Markdown"
    });
  } catch (error: any) {
    logger.error({ error: error.message }, "Failed to send status update");
  }
}
