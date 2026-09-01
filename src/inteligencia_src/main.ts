import { fetchCnpqOpportunities } from "./scrapers/cnpq.js";
import { fetchFinepOpportunities } from "./scrapers/finep.js";
import { fetchFapespOpportunities } from "./scrapers/fapesp.js";
import { fetchUnicampOpportunities } from "./scrapers/unicamp.js";
import { fetchCapesOpportunities } from "./scrapers/capes.js";
import { fetchEmbrapiiOpportunities } from "./scrapers/embrapii.js";
import { fetchCimatecOpportunities } from "./scrapers/senaicimatec.js";
import { fetchInovaOpportunities } from "./scrapers/inova.js";
import { scrapeArxiv } from "./scrapers/arxiv.js";
import { scrapeSemanticScholar } from "./scrapers/semanticscholar.js";
import { Opportunity, Priority, ProfileRequirements, RawOpportunity } from "./types.js";
import { appendAlerts, writeDailyDigest, writeWeeklyRanking } from "./utils/reporting.js";
import { classifyTrack, computeScore } from "./utils/scoring.js";
import { computeProfileScore, evaluateOpportunity, loadRequirements, passesHardFilters } from "./utils/requirements.js";
import { loadPrevious, saveCurrent } from "./utils/storage.js";
import { createLogger } from "./utils/logger.js";
import { opportunityKey, saveRunToDatabase } from "./utils/database.js";
import { writeStaticApiPayload } from "./utils/uiPayload.js";
import { analyzeOpportunityWithGemini } from "./utils/ai.js";
import { sendTelegramAlert } from "./utils/notifications.js";

const logger = createLogger("main");

function priorityByRequirement(score: number, req: ProfileRequirements): Priority {
  if (score >= req.scoring.thresholds.go) {
    return "aposta_principal";
  }
  if (score >= req.scoring.thresholds.watch) {
    return "aposta_tatica";
  }
  return "monitorar";
}

function enrichItems(items: RawOpportunity[], req: ProfileRequirements): Opportunity[] {
  return items.map((item) => {
    const source = item.source ?? "FINEP";
    const track = classifyTrack(item.title, item.snippet);
    const evalResult = evaluateOpportunity(item, req);
    const baselineBreakdown = computeScore({
      title: item.title,
      snippet: item.snippet,
      source,
      date: item.date,
      track
    });
    const profileScore = computeProfileScore(item, req);

    return {
      ...item,
      source,
      track,
      eligibility_summary: evalResult.eligibility.summary,
      eligibility_confidence: evalResult.eligibility.confidence,
      score_breakdown: {
        ...baselineBreakdown,
        total: profileScore
      },
      score: profileScore,
      priority: priorityByRequirement(profileScore, req)
    };
  });
}

async function main(): Promise<void> {
  logger.info("Starting inteligencIA pipeline");
  const startedAt = new Date().toISOString();

  const requirements = await loadRequirements();
  logger.info({ profile: requirements.profile_id }, "Loaded profile");
  const previous = await loadPrevious();
  logger.info({ count: previous.length }, "Loaded previous items");

  const collectorSpecs = [
    { name: "FINEP", fetcher: fetchFinepOpportunities },
    { name: "CNPq", fetcher: fetchCnpqOpportunities },
    { name: "FAPESP", fetcher: fetchFapespOpportunities },
    { name: "Unicamp", fetcher: fetchUnicampOpportunities },
    { name: "CAPES", fetcher: fetchCapesOpportunities },
    { name: "EMBRAPII", fetcher: fetchEmbrapiiOpportunities },
    { name: "CIMATECH", fetcher: fetchCimatecOpportunities },
    { name: "Inova Unicamp", fetcher: fetchInovaOpportunities },
    { name: "arXiv", fetcher: scrapeArxiv },
    { name: "Semantic Scholar", fetcher: scrapeSemanticScholar },
  ] as const;

  const settled = await Promise.allSettled(collectorSpecs.map((collector) => collector.fetcher()));
  const rawItems = settled.flatMap((result, index) => {
    const collectorName = collectorSpecs[index].name;
    if (result.status === "rejected") {
      const reason = result.reason instanceof Error ? result.reason.message : String(result.reason);
      logger.warn({ source: collectorName, error: reason }, "Source failed");
      return [];
    }

    logger.debug({ source: collectorName, count: result.value.length }, "Source fetched");
    return result.value;
  });

  const filtered = rawItems.filter((item) => passesHardFilters(item, requirements));
  logger.info({ total: rawItems.length, filtered: filtered.length }, "Items processed");

  const currentEnriched = enrichItems(filtered, requirements);

  // Enriquecimento com IA para itens promissores (acima do limiar de monitoramento)
  const promising = currentEnriched.filter((i) => i.score >= requirements.scoring.thresholds.watch);
  logger.info({ count: promising.length }, "Starting Gemini AI analysis for promising items");

  // Rate limiting: Gemini 2.0 Flash free tier = 15 RPM → ~4s entre chamadas
  const AI_DELAY_MS = 4000;
  for (const item of promising) {
    try {
      const aiResult = await analyzeOpportunityWithGemini(item, requirements);
      if (aiResult) {
        item.ai_analysis = aiResult;
        // Ajuste o score final: 40% heurística, 60% IA
        item.score = Math.round(item.score * 0.4 + aiResult.adherence_score * 0.6);
        item.priority = priorityByRequirement(item.score, requirements);
      }
    } catch (err) {
      logger.warn({ title: item.title }, "AI analysis failed for item");
    }
    // Respeitar rate limit da API Gemini
    await new Promise(resolve => setTimeout(resolve, AI_DELAY_MS));
  }

  // Mesclar com itens anteriores para evitar que chamadas sumam se um scraper falhar temporariamente
  const currentKeys = new Set(currentEnriched.map((i) => opportunityKey(i)));
  const itemsToKeepFromPrevious = previous.filter((p) => {
    // Manter se for de uma fonte que NÃO foi capturada nesta rodada OU se for um item ainda válido
    // Para simplificar, vamos manter todos os itens que ainda não "venceram" (lógica de data pode ser adicionada)
    return !currentKeys.has(opportunityKey(p));
  });

  const current = [...currentEnriched, ...itemsToKeepFromPrevious];

  const previousKeys = new Set(previous.map((i) => opportunityKey(i)));
  const fresh = currentEnriched.filter((i) => !previousKeys.has(opportunityKey(i)));
  const relevantMin = requirements.scoring.thresholds.watch;
  const relevantNew = fresh.filter((i) => i.score >= relevantMin);
  logger.info({ newAlerts: relevantNew.length }, "New items to alert");

  await saveCurrent(current);
  await saveRunToDatabase({
    current,
    rawCount: rawItems.length,
    freshCount: fresh.length,
    alertCount: relevantNew.length,
    startedAt
  });
  await appendAlerts("reports/alerts.md", relevantNew);
  await writeWeeklyRanking(current);
  await writeDailyDigest(current, relevantNew, requirements, {
    rawCount: rawItems.length,
    freshCount: fresh.length,
    alertCount: relevantNew.length
  });
  await writeStaticApiPayload(current, undefined, {
    searchedCount: rawItems.length,
    freshQualifiedCount: fresh.length,
    alertCount: relevantNew.length,
    rawItems: rawItems
  });

  // Alertas em Tempo Real (Score > 90)
  const highPriority = relevantNew.filter(i => i.score >= 90);
  if (highPriority.length > 0) {
    logger.info({ count: highPriority.length }, "Sending high-priority Telegram alerts");
    for (const opp of highPriority) {
      await sendTelegramAlert(opp);
    }
  }

  // Inteligência legislativa removida: foco exclusivo em editais de fomento
  logger.info({ total: current.length, new: relevantNew.length }, "Pipeline completed");
}

main().catch((err: unknown) => {
  const message = err instanceof Error ? err.stack ?? err.message : String(err);
  logger.error({ error: message }, "Pipeline failed");
  process.exitCode = 1;
});
