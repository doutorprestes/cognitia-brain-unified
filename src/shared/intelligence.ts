import { createLogger } from "./logger.js";

const logger = createLogger("intelligence");

// Legislative sources (Camara/Senado) removed per project focus on actual grants.
// Intelligence module retained for future grant-based trend analysis.

export interface LegislativeInsight {
  id: string | number;
  title: string;
  type: string;
  year: number;
  url: string;
  source: string;
}

export interface IntelligenceTrend {
  topic: string;
  impact: string;
  relevance: number;
  description: string;
}

export interface IntelligencePayload {
  last_updated: string;
  insights: LegislativeInsight[];
  trends: IntelligenceTrend[];
}

export async function fetchLegislativeInsights(): Promise<LegislativeInsight[]> {
  logger.info("Legislative insights disabled: focus on grant opportunities only");
  return [];
}

export async function generateTrends(_insights: LegislativeInsight[]): Promise<IntelligenceTrend[]> {
  logger.info("Trend generation disabled: no legislative data source");
  return [];
}

export async function writeIntelligencePayload(payload: IntelligencePayload, outputDir: string): Promise<void> {
  const { writeFile, mkdir } = await import("node:fs/promises");
  const { join } = await import("node:path");

  await mkdir(outputDir, { recursive: true });
  await writeFile(join(outputDir, "intelligence.json"), JSON.stringify(payload, null, 2), "utf8");
}
