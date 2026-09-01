import { GoogleGenerativeAI, SchemaType } from "@google/generative-ai";
import { Opportunity, ProfileRequirements, RawOpportunity } from "../types.js";
import { createLogger } from "./logger.js";

const logger = createLogger("ai");

const schema = {
  description: "Análise profunda de oportunidade de fomento para pesquisador Unicamp",
  type: SchemaType.OBJECT,
  properties: {
    executive_summary: {
      type: SchemaType.STRING,
      description: "Síntese executiva original (até 140 caracteres). NÃO repita o texto do edital. Foque no propósito real e entregáveis.",
    },
    adherence_score: {
      type: SchemaType.NUMBER,
      description: "Nota de 0 a 100 de fit com o projeto de Campo Mórfico Simulado / MARL / Robótica / Startup Deep Tech.",
    },
    justification: {
      type: SchemaType.STRING,
      description: "Explicação detalhada e original de 'Por que este edital é crucial agora?' para o projeto de Campo Mórfico. NÃO cite scores numéricos ou eixos temáticos.",
    },
    eligibility_criteria: {
      type: SchemaType.ARRAY,
      items: { type: SchemaType.STRING },
      description: "Lista de 3 a 5 critérios concretos extraídos (ex: 'Exige mestrado em andamento', 'Faturamento até X'). Evite recomendações genéricas.",
    },
    themes: {
      type: SchemaType.ARRAY,
      items: { type: SchemaType.STRING },
      description: "Eixos estratégicos (IA / MARL, Robótica, Startup, Academia).",
    },
    keywords: {
      type: SchemaType.ARRAY,
      items: { type: SchemaType.STRING },
      description: "5 a 8 palavras-chave técnicas e semânticas (Tecnologias, Nomes Próprios). EXCLUA stopwords e termos genéricos.",
    },
    type: {
      type: SchemaType.STRING,
      enum: ["bolsa-pessoal", "grant-projeto"],
      description: "Bolsa (sustento pessoal) ou Grant (recursos para o projeto).",
    },
    funding_amount: {
      type: SchemaType.STRING,
      description: "Valor do fomento extraído explicitamente do texto. Use 'A definir no edital' APENAS se não houver valor citado.",
    }
  },
  required: ["executive_summary", "adherence_score", "justification", "eligibility_criteria", "themes", "keywords", "type", "funding_amount"],
} as const;

async function sleep(ms: number) {
  return new Promise(resolve => setTimeout(resolve, ms));
}

export async function analyzeOpportunityWithGemini(
  item: RawOpportunity,
  req: ProfileRequirements,
  retries = 2
): Promise<Opportunity["ai_analysis"] | null> {
  const apiKey = process.env.GEMINI_API_KEY;
  if (!apiKey || apiKey === "sua-chave-api-aqui") {
    logger.warn("GEMINI_API_KEY não configurada. Pulando análise de IA.");
    return null;
  }

  // Hard rejection of residual Ethics terms at the AI level
  const lowerTitle = item.title.toLowerCase();
  const lowerSnippet = item.snippet.toLowerCase();
  if (lowerTitle.includes("ética") || lowerTitle.includes("responsible ai") || lowerSnippet.includes("especialização em ética")) {
    logger.debug({ title: item.title }, "AI Analysis skipped: ethics-related item detected and rejected");
    return null;
  }

  try {
    const genAI = new GoogleGenerativeAI(apiKey);
    const model = genAI.getGenerativeModel({
      model: "gemini-2.5-flash-lite",
      generationConfig: {
        responseMimeType: "application/json",
        responseSchema: schema as any,
      },
    });

    const prompt = `
      Você é um Analista de Fomento Sênior. Sua missão é avaliar se este edital serve para o projeto de Mestrado na Unicamp de José Augusto Prestes.

      CONTEXTO DO USUÁRIO (Mestrado v4):
      - Projeto: Aprendizado Coletivo em Robótica via Campo Mórfico Simulado.
      - Tecnologias: MARL (Multi-Agent Reinforcement Learning), Robótica Coletiva, Thin Agents, Remote Brain, Cognição Distribuída.
      - Instituição: FEEC / Unicamp.
      - Objetivos: 1) Bolsas de mestrado para o autor; 2) Verba para startup/spin-off baseada no projeto.
      - REJEIÇÃO MANDATÓRIA: Ignore editais que foquem exclusivamente em Humanas, Ética da IA, Direito ou Artes.

      OPORTUNIDADE:
      Título: ${item.title}
      Texto Coletado (pode incluir fragmentos de links e anexos): 
      ---
      ${item.snippet.substring(0, 5000)}
      ---

      INSTRUÇÕES ESTRITAS:
      1. SUMÁRIO EXECUTIVO: Gere um texto coeso de ATÉ 140 CARACTERES, sem repetições. Sintetize a essência técnica e o propósito.
      2. ELEGIBILIDADE: Extraia 3 a 5 regras CONCRETAS baseadas no texto. Não dê recomendações genéricas como "verifique o edital".
      3. JUSTIFICATIVA ESTRATÉGICA: Responda de forma original: "Por que este edital é crucial agora para o projeto Campo Mórfico?". NÃO repita scores ou temas.
      4. VALOR DO FOMENTO: Procure ativamente cifras e moedas (R$, $, €) no texto. Use "A definir no edital" APENAS se for impossível encontrar.
      5. PALAVRAS-CHAVE: Liste de 5 a 8 termos de alto valor (tecnologias, instituições, conceitos chave). Exclua web stopwords (ex: "clique aqui", "veja mais").
      
      Retorne apenas o JSON validando o schema.
    `;

    const result = await model.generateContent(prompt);
    const response = result.response;
    const text = response.text();
    const data = JSON.parse(text);

    // Final sanity check on AI score for ethics items that might have slipped through
    if (data.executive_summary.toLowerCase().includes("ética") && data.adherence_score > 30) {
      data.adherence_score = 10;
    }

    return data as Opportunity["ai_analysis"];
  } catch (error: any) {
    if (error.status === 429 && retries > 0) {
      logger.warn({ title: item.title }, "AI Rate limited, retrying in 5s...");
      await sleep(5000);
      return analyzeOpportunityWithGemini(item, req, retries - 1);
    }
    logger.error({ error: error.message, title: item.title }, "Falha na análise do Gemini");
    return null;
  }
}
