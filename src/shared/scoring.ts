import {
  NEGATIVE_KEYWORDS,
  SCORE_WEIGHTS,
  TRACK_A_KEYWORDS,
  TRACK_B_KEYWORDS
} from "../config.js";
import { Priority, ScoreBreakdown, Track } from "../types.js";

function normalize(text: string): string {
  return text
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "")
    .toLowerCase();
}

function containsAny(text: string, words: readonly string[]): number {
  const t = normalize(text);
  return words.reduce((acc, w) => (t.includes(normalize(w)) ? acc + 1 : acc), 0);
}

function parsePtBrDate(value: string): Date | null {
  const m = value.match(/(\d{2})\/(\d{2})\/(\d{4})/);
  if (!m) {
    return null;
  }

  const date = new Date(Number(m[3]), Number(m[2]) - 1, Number(m[1]));
  return Number.isNaN(date.getTime()) ? null : date;
}

export function classifyTrack(title: string, snippet: string): Track {
  const blob = `${title} ${snippet}`;
  const aHits = containsAny(blob, TRACK_A_KEYWORDS);
  const bHits = containsAny(blob, TRACK_B_KEYWORDS);

  if (aHits > bHits) {
    return "A";
  }
  if (bHits > aHits) {
    return "B";
  }
  return "A/B";
}

export function computeScore(input: {
  title: string;
  snippet: string;
  source: string;
  date: string;
  track: Track;
}): ScoreBreakdown {
  const text = `${input.title} ${input.snippet}`;
  const negHits = containsAny(text, NEGATIVE_KEYWORDS);

  let fit = Math.min(100, containsAny(text, [...TRACK_A_KEYWORDS, ...TRACK_B_KEYWORDS]) * 20);
  fit = Math.max(0, fit - negHits * 20);

  const eligibility = input.source === "FINEP" ? 80 : 60;
  const keywordHits = containsAny(text, [...TRACK_A_KEYWORDS, ...TRACK_B_KEYWORDS]);

  let approvalProbability = Math.min(90, 40 + keywordHits * 10 - negHits * 10);
  approvalProbability = Math.max(0, approvalProbability);

  let effortVsDeadline = 60;
  const deadline = parsePtBrDate(input.date);
  if (deadline) {
    const now = new Date();
    now.setHours(0, 0, 0, 0);
    const delta = Math.floor((deadline.getTime() - now.getTime()) / 86400000);
    if (delta >= 45) {
      effortVsDeadline = 90;
    } else if (delta >= 21) {
      effortVsDeadline = 75;
    } else if (delta >= 10) {
      effortVsDeadline = 60;
    } else if (delta >= 0) {
      effortVsDeadline = 40;
    } else {
      effortVsDeadline = 0;
    }
  }

  const impact = input.track === "A/B" ? 65 : 75;
  const total = Math.round(
    fit * (SCORE_WEIGHTS.fit / 100) +
      eligibility * (SCORE_WEIGHTS.eligibility / 100) +
      approvalProbability * (SCORE_WEIGHTS.approval_probability / 100) +
      effortVsDeadline * (SCORE_WEIGHTS.effort_vs_deadline / 100) +
      impact * (SCORE_WEIGHTS.impact / 100)
  );

  return {
    fit,
    eligibility,
    approval_probability: approvalProbability,
    effort_vs_deadline: effortVsDeadline,
    impact,
    total
  };
}

export function scoreLabel(total: number): Priority {
  if (total >= 75) {
    return "aposta_principal";
  }
  if (total >= 60) {
    return "aposta_tatica";
  }
  return "monitorar";
}
