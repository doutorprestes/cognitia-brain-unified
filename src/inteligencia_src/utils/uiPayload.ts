import { mkdir, writeFile } from "node:fs/promises";
import { join } from "node:path";

import { Opportunity } from "../types.js";
import { loadOpportunityDecisions, loadOpportunityEvents, opportunityKey } from "./database.js";

const DATA_DIR = process.env.DATA_DIR || "data";

export type UiOpportunity = {
  id: string;
  title: string;
  source: "FAPESP" | "FINEP" | "CNPq" | "CAPES" | "EMBRAPII" | "SENAI CIMATEC" | "Inova Unicamp" | "Empresas" | "Internacional" | "Outras";
  type: "bolsa-pessoal" | "grant-projeto";
  track: "Acadêmica" | "Empreendedora" | "A/B";
  deadline: string;
  deadlineCategory: "urgente" | "30-dias" | "60-dias" | "90-dias+";
  adherence: number;
  financialSupport: "Alto" | "Médio" | "Baixo";
  priority: number;
  rank: number;
  isHighPriority: boolean;
  url: string;
  summary: string;
  eligibility: string[];
  amount: string;
  themes: string[];
  justification: string;
  keywords: string[];
  decision: "unreviewed" | "apply" | "watch" | "dismiss" | "favorite";
  notes?: string;
  events?: any[];
  effort: "Baixo" | "Médio" | "Alto";
};

export type UiStatus = {
  isLoading: boolean;
  lastUpdate: string | null;
  newCount: Record<UiOpportunity["source"], number>;
  sourceBreakdown: Record<UiOpportunity["source"], number>;
  searchedCount: number;
  qualifiedCount: number;
  freshQualifiedCount: number;
  alertCount: number;
  eligibilityRate: number;
  hasError: boolean;
  errorMessage?: string;
};

function parsePtBrDate(rawDate: string): Date | null {
  const m = rawDate.match(/(\d{2})\/(\d{2})\/(\d{4})/);
  if (!m) {
    return null;
  }
  const date = new Date(Number(m[3]), Number(m[2]) - 1, Number(m[1]));
  return Number.isNaN(date.getTime()) ? null : date;
}

function deadlineCategory(rawDate: string): UiOpportunity["deadlineCategory"] {
  const parsed = parsePtBrDate(rawDate);
  if (!parsed) {
    return "90-dias+";
  }
  const today = new Date();
  today.setHours(0, 0, 0, 0);
  const days = Math.floor((parsed.getTime() - today.getTime()) / 86400000);
  if (days <= 15) {
    return "urgente";
  }
  if (days <= 30) {
    return "30-dias";
  }
  if (days <= 60) {
    return "60-dias";
  }
  return "90-dias+";
}

function sourceToUi(source: string, title: string): UiOpportunity["source"] {
  const s = (source || "").toLowerCase();
  const t = (title || "").toLowerCase();
  if (s.includes("fapesp")) return "FAPESP";
  if (s.includes("finep")) return "FINEP";
  if (s.includes("cnpq")) return "CNPq";
  if (s.includes("capes")) return "CAPES";
  if (s.includes("embrapii")) return "EMBRAPII";
  if (s.includes("cimatec")) return "SENAI CIMATEC";
  if (s.includes("inova") && s.includes("unicamp")) return "Inova Unicamp";
  if (s.includes("grantsgov") || s.includes("ukri") || s.includes("euraxess")) return "Internacional";
  if (["google", "nvidia", "aws", "embraer", "santander"].some((k) => t.includes(k))) return "Empresas";
  return "Outras";
}

function classifyType(item: Opportunity): UiOpportunity["type"] {
  const text = `${item.title} ${item.snippet} ${item.opportunity_type ?? ""}`.toLowerCase();
  if (["bolsa", "fellowship", "studentship", "scholarship", "mestrado", "doutorado"].some((term) => text.includes(term))) {
    return "bolsa-pessoal";
  }
  return "grant-projeto";
}

function sustainment(type: UiOpportunity["type"], source: string, title: string): UiOpportunity["financialSupport"] {
  const text = `${source} ${title}`.toLowerCase();
  if (type === "bolsa-pessoal") {
    return ["fapesp", "cnpq", "capes", "fellowship", "studentship", "scholarship"].some((k) => text.includes(k)) ? "Alto" : "Médio";
  }
  return ["pipe", "finep", "grant", "inov", "pesquisa"].some((k) => text.includes(k)) ? "Alto" : "Médio";
}

function stripHtml(text: string): string {
  if (!text) return "";
  
  // 1. Basic HTML stripping
  let clean = text
    .replace(/<[^>]*>/g, " ")
    .replace(/&nbsp;/g, " ")
    .replace(/&amp;/g, "&")
    .replace(/&pound;/g, "GBP ");

  // 2. Aggressive multi-line removal of the social/meta block (matching Python logic)
  clean = clean.replace(/Compartilhe:.*?(\d{2}h\d{2})/gs, " ");
  
  // 3. Resilient fallback patterns
  const noisePatterns = [
    /new ClipboardJS\(.*?\)\s*;?/gis,
    /\{ text: function\(trigger\).*?\} \);/gs,
    /Compartilhe por (Facebook|Twitter|LinkedIn|WhatsApp)/gi,
    /link para Copiar para área de transferência/gi,
    /Publicado em \d{2}\/\d{2}\/\d{4}.*?\d{2}h\d{2}/gi,
    /Atualizado em \d{2}\/\d{2}\/\d{4}.*?\d{2}h\d{2}/gi,
    /Compartilhe:/gi
  ];

  for (const pattern of noisePatterns) {
    clean = clean.replace(pattern, "");
  }

  clean = clean.replace(/^.*?Programa PCI/i, "Programa PCI");

  return clean.replace(/\w{1,2}\/\d{4}/g, "").replace(/\s+/g, " ").trim();
}

function themes(item: Opportunity): string[] {
  if (item.ai_analysis?.themes) return item.ai_analysis.themes;
  
  const t: string[] = [];
  const text = `${item.title} ${item.snippet}`.toLowerCase();
  
  if (text.match(/marl|multiagente|inteligência|ia|aprendizado/i)) t.push("IA / MARL");
  if (text.match(/rob|robot|humanoide|autônomo/i)) t.push("Robótica");
  if (text.match(/startup|empresa|deep tech|inovação|pipe|aceleração/i)) t.push("Startup");
  if (text.match(/mestrado|bolsa|pesquisa|academia|acadêmico/i)) t.push("Academia");
  
  if (t.length === 0) t.push("Fomento");
  return t;
}

function keywordList(item: Opportunity): string[] {
  const terms = new Set<string>();
  for (const token of `${item.title} ${item.snippet}`.split(/\W+/)) {
    const clean = token.trim();
    if (clean.length >= 5 && terms.size < 8) {
      terms.add(clean);
    }
  }
  return [...terms];
}

function smartSummarize(text: string): string {
  const cleaned = stripHtml(text);
  if (!cleaned) return "Descrição não informada pelo portal de origem.";
  
  if (cleaned.length <= 400) return cleaned;

  const sub = cleaned.substring(0, 400);
  const lastPeriod = sub.lastIndexOf(".");
  if (lastPeriod > 250) {
    return sub.substring(0, lastPeriod + 1);
  }
  
  const lastSpace = sub.lastIndexOf(" ");
  return sub.substring(0, lastSpace > 0 ? lastSpace : 400) + "...";
}

export type UiPayloadStats = {
  searchedCount?: number;
  freshQualifiedCount?: number;
  alertCount?: number;
  rawItems?: any[];
};

export async function buildUiPayload(
  items: Opportunity[],
  stats: UiPayloadStats = {}
): Promise<{ opportunities: UiOpportunity[]; status: UiStatus }> {
  const decisions = await loadOpportunityDecisions();
  const events = await loadOpportunityEvents();
  
  // Sort by score to calculate rank
  const sortedItems = [...items].sort((a, b) => b.score - a.score || a.title.localeCompare(b.title));

  const opportunities = sortedItems.map((item, index) => {
    const source = sourceToUi(item.source, item.title);
    const type = item.ai_analysis?.type ?? classifyType(item);
    const key = opportunityKey(item);
    const decision = decisions.get(key);
    const history = events.get(key) || [];
    const track: UiOpportunity["track"] = item.track === "A" ? "Acadêmica" : item.track === "B" ? "Empreendedora" : "A/B";
    const stopWords = new Set(["facebook", "twitter", "linkedin", "whatsapp", "compartilhe", "programa", "chamada", "fndct", "new", "clipboardjs"]);

    return {
      id: key,
      title: item.title,
      source,
      type,
      track,
      deadline: item.date || "A confirmar",
      deadlineCategory: deadlineCategory(item.date),
      adherence: item.score,
      financialSupport: sustainment(type, item.source, item.title),
      priority: index + 1,
      rank: index + 1,
      isHighPriority: item.priority === "aposta_principal",
      url: item.link,
      summary: item.ai_analysis?.executive_summary ?? smartSummarize(item.snippet),
      eligibility: item.ai_analysis?.eligibility_criteria ?? [
        "Verificar edital completo no link oficial.",
        "Confirmar requisitos institucionais e de titulação.",
        "Conferir documentação obrigatória e cronograma."
      ],
      amount: item.ai_analysis?.funding_amount ?? item.funding_amount ?? "A definir no edital",
      themes: themes(item),
      justification: item.ai_analysis?.justification ?? `Fit de ${item.score}% identificado com o seu perfil técnico e objetivos de mestrado.`,
      keywords: (item.ai_analysis?.keywords ?? keywordList(item)).filter(kw => !stopWords.has(kw.toLowerCase())),
      decision: decision?.decision ?? "unreviewed",
      notes: decision?.notes,
      events: history,
      effort: type === "bolsa-pessoal" ? "Médio" : "Alto"
    } satisfies UiOpportunity;
  });

  const newCounts: UiStatus["newCount"] = {
    FAPESP: 0, FINEP: 0, CNPq: 0, CAPES: 0, EMBRAPII: 0, 'SENAI CIMATEC': 0, 'Inova Unicamp': 0, Empresas: 0, Internacional: 0, Outras: 0
  };
  for (const item of opportunities) {
    newCounts[item.source] += 1;
  }

  const rawBreakdown: Record<string, number> = {
    FAPESP: 0, FINEP: 0, CNPq: 0, CAPES: 0, EMBRAPII: 0, 'SENAI CIMATEC': 0, 'Inova Unicamp': 0, Empresas: 0, Internacional: 0, Outras: 0
  };
  if (stats.rawItems) {
    for (const item of stats.rawItems) {
      const src = sourceToUi(item.source || "Outras", item.title || "");
      rawBreakdown[src] = (rawBreakdown[src] || 0) + 1;
    }
  }

  return {
    opportunities,
    status: {
      isLoading: false,
      lastUpdate: new Date().toISOString(),
      newCount: newCounts,
      sourceBreakdown: rawBreakdown as UiStatus["sourceBreakdown"],
      searchedCount: stats.searchedCount ?? items.length,
      qualifiedCount: items.length,
      freshQualifiedCount: stats.freshQualifiedCount ?? 0,
      alertCount: stats.alertCount ?? 0,
      eligibilityRate: (stats.searchedCount ?? items.length) > 0 ? Math.round((items.length / (stats.searchedCount ?? items.length)) * 100) : 0,
      hasError: false
    }
  };
}

export async function writeStaticApiPayload(
  items: Opportunity[],
  outputDir = join(DATA_DIR, "static-api"),
  stats: UiPayloadStats = {}
): Promise<void> {
  const payload = await buildUiPayload(items, stats);
  await mkdir(outputDir, { recursive: true });
  await writeFile(`${outputDir}/opportunities.json`, `${JSON.stringify(payload.opportunities, null, 2)}\n`, "utf8");
  await writeFile(`${outputDir}/status.json`, `${JSON.stringify(payload.status, null, 2)}\n`, "utf8");
}
