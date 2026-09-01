import { Opportunity, ProfileRequirements, RawOpportunity } from "../types.js";
import { createLogger } from "./logger.js";

const logger = createLogger("ai");

const OPENCODE_BASE_URL = process.env.OPENCODE_BASE_URL || "https://opencode.ai/zen/go/v1";
const OPENCODE_API_KEY = process.env.OPENCODE_GO_API_KEY || "";
const AI_MODEL = process.env.INTELIGENCIA_AI_MODEL || "deepseek-v4-flash";

async function sleep(ms: number) {
  return new Promise(resolve => setTimeout(resolve, ms));
}

const SYSTEM_PROMPT = `Você é um Analista de Fomento Sênior. Sua missão é avaliar editais para o projeto de Mestrado na Unicamp de José Augusto Prestes.

CONTEXTO DO USUÁRIO:
- Projeto: Aprendizado Coletivo em Robótica via Campo Mórfico Simulado.
- Tecnologias: MARL (Multi-Agent Reinforcement Learning), Robótica Coletiva, Thin Agents, Remote Brain, Cognição Distribuída.
- Instituição: FEEC / Unicamp.
- Objetivos: 1) Bolsas de mestrado para o autor; 2) Verba para startup/spin-off baseada no projeto.
- REJEIÇÃO MANDATÓRIA: Ignore editais que foquem exclusivamente em Humanas, Ética da IA, Direito ou Artes.

Retorne APENAS um JSON válido com esta estrutura exata:
{
  "executive_summary": "string (250-500 chars, síntese original, sem repetir o texto)",
  "adherence_score": number (0-100, fit com o projeto),
  "justification": "string (explicação original de por que este edital é crucial agora)",
  "eligibility_criteria": ["string (3-5 critérios concretos extraídos do texto)"],
  "themes": ["string (eixos: IA/MARL, Robótica, Startup, Academia)"],
  "keywords": ["string (5-8 termos técnicos de alto valor)"],
  "type": "bolsa-pessoal" | "grant-projeto",
  "funding_amount": "string (valor extraído ou 'A definir no edital')"
}`;

export async function analyzeOpportunityWithGemini(
  item: RawOpportunity,
  req: ProfileRequirements,
  retries = 2
): Promise<Opportunity["ai_analysis"] | null> {
  if (!OPENCODE_API_KEY) {
    logger.warn("OPENCODE_GO_API_KEY não configurada. Pulando análise de IA.");
    return null;
  }

  // Hard rejection of residual Ethics terms at the AI level
  const lowerTitle = item.title.toLowerCase();
  const lowerSnippet = item.snippet.toLowerCase();
  if (lowerTitle.includes("ética") || lowerTitle.includes("responsible ai") || lowerSnippet.includes("especialização em ética")) {
    logger.debug({ title: item.title }, "AI Analysis skipped: ethics-related item detected and rejected");
    return null;
  }

  const userPrompt = `OPORTUNIDADE:
Título: ${item.title}
Texto Coletado (pode incluir fragmentos de links e anexos): 
---
${item.snippet.substring(0, 5000)}
---

Analise esta oportunidade e retorne APENAS o JSON.`;

  try {
    const response = await fetch(`${OPENCODE_BASE_URL}/chat/completions`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "Authorization": `Bearer ${OPENCODE_API_KEY}`,
      },
      body: JSON.stringify({
        model: AI_MODEL,
        messages: [
          { role: "system", content: SYSTEM_PROMPT },
          { role: "user", content: userPrompt },
        ],
        response_format: { type: "json_object" },
        temperature: 0.3,
        max_tokens: 2000,
      }),
      signal: AbortSignal.timeout(30000),
    });

    if (!response.ok) {
      const errText = await response.text().catch(() => "");
      const isRateLimited = response.status === 429;

      if (isRateLimited && retries > 0) {
        const waitMs = (3 - retries) * 7000 + 5000;
        logger.warn({ title: item.title, retries, waitMs, status: response.status }, "AI Rate limited, retrying...");
        await sleep(waitMs);
        return analyzeOpportunityWithGemini(item, req, retries - 1);
      }

      throw new Error(`HTTP ${response.status}: ${errText.substring(0, 200)}`);
    }

    const json: any = await response.json();
    const content = json.choices?.[0]?.message?.content;
    if (!content) {
      throw new Error("Resposta vazia do modelo");
    }

    const data = JSON.parse(content);

    // Final sanity check on AI score for ethics items that might have slipped through
    if (data.executive_summary?.toLowerCase().includes("ética") && data.adherence_score > 30) {
      data.adherence_score = 10;
    }

    return data as Opportunity["ai_analysis"];
  } catch (error: any) {
    logger.error({ error: error.message, title: item.title }, "Falha na análise de IA");
    return null;
  }
}
