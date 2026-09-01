import { mkdir, writeFile } from "node:fs/promises";
import { join, dirname } from "node:path";

import { Opportunity, ProfileRequirements } from "../types.js";

const DATA_DIR = process.env.DATA_DIR || ".";
const REPORTS_DIR = join(DATA_DIR, "reports");

function nowPtBr(): string {
  return new Intl.DateTimeFormat("pt-BR", {
    dateStyle: "short",
    timeStyle: "short"
  }).format(new Date());
}

export async function writeWeeklyRanking(
  items: Opportunity[],
  path = join(REPORTS_DIR, "weekly_ranking.md")
): Promise<void> {
  await mkdir(REPORTS_DIR, { recursive: true });
  const sorted = [...items].sort((a, b) => b.score - a.score);

  const lines = [
    "# Ranking semanal de oportunidades",
    "",
    `Gerado em: ${nowPtBr()}`,
    "",
    "| Rank | Fonte | Trilha | Score | Classe | Prazo | Titulo |",
    "|---:|---|---|---:|---|---|---|"
  ];

  sorted.forEach((item, i) => {
    lines.push(
      `| ${i + 1} | ${item.source} | ${item.track} | ${item.score} | ${item.priority} | ${item.date || "-"} | [${item.title}](${item.link}) |`
    );
  });

  await writeFile(path, `${lines.join("\n")}\n`, "utf8");
}

export async function appendAlerts(path: string, items: Opportunity[]): Promise<void> {
  if (items.length === 0) {
    return;
  }

  const targetPath = path.startsWith("/") ? path : join(DATA_DIR, path);
  await mkdir(dirname(targetPath), { recursive: true });
  const lines = items.map(
    (it) =>
      `- **${it.date || "-"}** [${it.source}|${it.track}] score=${it.score} (${it.priority}): [${it.title}](${it.link})`
  );

  const { appendFile } = await import("node:fs/promises");
  await appendFile(targetPath, `${lines.join("\n")}\n`, "utf8");
}

export async function writeDailyDigest(
  current: Opportunity[],
  fresh: Opportunity[],
  requirements: ProfileRequirements,
  statsOrPath: { rawCount?: number; freshCount?: number; alertCount?: number } | string = {},
  path = join(REPORTS_DIR, "daily_digest.md")
): Promise<void> {
  await mkdir(REPORTS_DIR, { recursive: true });
  const stats = typeof statsOrPath === "string" ? {} : statsOrPath;
  const outputPath = typeof statsOrPath === "string" ? statsOrPath : path;

  const finalPath = outputPath.startsWith("/") ? outputPath : join(DATA_DIR, outputPath);
  await mkdir(dirname(finalPath), { recursive: true });

  const topCurrent = [...current].sort((a, b) => b.score - a.score).slice(0, 10);
  const topFresh = [...fresh].sort((a, b) => b.score - a.score).slice(0, 10);
  const rawCount = stats.rawCount ?? current.length;
  const eligibilityRate = rawCount > 0 ? Math.round((current.length / rawCount) * 100) : 0;
  const bySource = current.reduce<Record<string, number>>((acc, item) => {
    acc[item.source] = (acc[item.source] ?? 0) + 1;
    return acc;
  }, {});

  const lines = [
    "# GrantWatch Daily Digest",
    "",
    `Gerado em: ${nowPtBr()}`,
    `Perfil: ${requirements.profile_id}`,
    "",
    `Objetivo: ${requirements.objective}`,
    "",
    "## Resumo",
    "",
    `- Oportunidades identificadas: ${rawCount}`,
    `- Oportunidades qualificadas: ${current.length}`,
    `- Taxa de elegibilidade: ${current.length}/${rawCount} (${eligibilityRate}%)`,
    `- Novas oportunidades qualificadas: ${fresh.length}`,
    `- Fontes com resultados: ${Object.entries(bySource).map(([source, count]) => `${source}=${count}`).join(", ") || "-"}`,
    "",
    "## Novas oportunidades",
    ""
  ];

  if (topFresh.length === 0) {
    lines.push("Nenhuma oportunidade nova acima do limiar de alerta hoje.");
  } else {
    topFresh.forEach((item, index) => {
      lines.push(`${index + 1}. **${item.source}** score=${item.score} ${item.priority} prazo=${item.date || "-"}: [${item.title}](${item.link})`);
      if (item.eligibility_summary) {
        lines.push(`   - Elegibilidade: ${item.eligibility_summary}`);
      }
    });
  }

  lines.push("", "## Top oportunidades monitoradas", "");
  if (topCurrent.length === 0) {
    lines.push("Nenhuma oportunidade qualificada no momento.");
  } else {
    topCurrent.forEach((item, index) => {
      lines.push(`${index + 1}. **${item.source}** score=${item.score} ${item.priority} prazo=${item.date || "-"}: [${item.title}](${item.link})`);
    });
  }

  await writeFile(finalPath, `${lines.join("\n")}\n`, "utf8");
}
