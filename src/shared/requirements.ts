import { readFile } from "node:fs/promises";
import { join } from "node:path";

import { EligibilityAssessment, ProfileRequirements, RawOpportunity } from "../types.js";
import { domainRelevance } from "./domain.js";
import { extractEligibilityAssessment } from "./eligibility.js";
import { acceptsBrazilCampinasApplicant } from "./filters.js";

function normalize(text: string): string {
  return text
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "")
    .toLowerCase();
}

function parsePtBrDate(value: string): Date | null {
  const m = value.match(/(\d{2})\/(\d{2})\/(\d{4})/);
  if (!m) {
    return null;
  }
  const date = new Date(Number(m[3]), Number(m[2]) - 1, Number(m[1]));
  return Number.isNaN(date.getTime()) ? null : date;
}

function daysUntil(dateStr: string): number | null {
  const d = parsePtBrDate(dateStr);
  if (!d) {
    return null;
  }
  const now = new Date();
  now.setHours(0, 0, 0, 0);
  return Math.floor((d.getTime() - now.getTime()) / 86400000);
}

function countMatches(text: string, terms: readonly string[]): number {
  const t = normalize(text);
  return terms.reduce((acc, term) => {
    const normalizedTerm = normalize(term);
    if (normalizedTerm.length <= 3) {
      const pattern = new RegExp(`(^|\\W)${normalizedTerm.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")}(\\W|$)`);
      return pattern.test(t) ? acc + 1 : acc;
    }
    return t.includes(normalizedTerm) ? acc + 1 : acc;
  }, 0);
}

function anyMatch(text: string, terms: readonly string[]): boolean {
  return countMatches(text, terms) > 0;
}

const DATA_DIR = process.env.DATA_DIR || ".";

export async function loadRequirements(path = join(DATA_DIR, "data", "mestrado_profile_requirements.json")): Promise<ProfileRequirements> {
  const raw = await readFile(path, "utf8");
  return JSON.parse(raw) as ProfileRequirements;
}

export function passesHardFilters(item: RawOpportunity, req: ProfileRequirements): boolean {
  return evaluateOpportunity(item, req).passes_hard_filters;
}

export function evaluateOpportunity(
  item: RawOpportunity,
  req: ProfileRequirements
): {
  passes_hard_filters: boolean;
  technical_hits: number;
  context_hits: number;
  audience_hits: number;
  eligibility: EligibilityAssessment;
} {
  const text = `${item.title} ${item.snippet}`;
  const hard = req.hard_filters;
  const t = normalize(text);
  const eligibility = extractEligibilityAssessment(item);
  const domain = domainRelevance(item);
  const isInternationalSource = ["UKRI", "GrantsGov", "Euraxess"].includes(item.source ?? "");

  if (anyMatch(text, hard.exclude_any)) {
    return {
      passes_hard_filters: false,
      technical_hits: 0,
      context_hits: 0,
      audience_hits: 0,
      eligibility
    };
  }
  if (isInternationalSource && !domain.in_domain) {
    return {
      passes_hard_filters: false,
      technical_hits: 0,
      context_hits: 0,
      audience_hits: 0,
      eligibility
    };
  }
  if (!acceptsBrazilCampinasApplicant(item)) {
    return {
      passes_hard_filters: false,
      technical_hits: 0,
      context_hits: 0,
      audience_hits: 0,
      eligibility
    };
  }
  const technicalHits = countMatches(text, hard.include_any_technical_core);
  const contextHits = countMatches(text, hard.include_any_application_context);
  const audienceHits = countMatches(text, hard.required_audience_any) + (eligibility.audience_matches.length > 0 ? 1 : 0);
  const intlAudienceHints =
    t.includes("scholarship") ||
    t.includes("studentship") ||
    t.includes("fellowship") ||
    t.includes("phd") ||
    t.includes("doctoral");

  const profileStrictPass = technicalHits >= 1 && (contextHits >= 1 || audienceHits >= 1 || intlAudienceHints);
  const broaderTechPass = contextHits >= 2 && (audienceHits >= 1 || intlAudienceHints);
  const intlAcademicPass = contextHits >= 1 && intlAudienceHints;
  if (!profileStrictPass && !intlAcademicPass && !broaderTechPass) {
    return {
      passes_hard_filters: false,
      technical_hits: technicalHits,
      context_hits: contextHits,
      audience_hits: audienceHits,
      eligibility
    };
  }

  const remainingDays = daysUntil(item.date);
  if (remainingDays !== null && remainingDays < hard.deadline_min_days) {
    return {
      passes_hard_filters: false,
      technical_hits: technicalHits,
      context_hits: contextHits,
      audience_hits: audienceHits,
      eligibility
    };
  }

  return {
    passes_hard_filters: true,
    technical_hits: technicalHits,
    context_hits: contextHits,
    audience_hits: audienceHits,
    eligibility
  };
}

export function computeProfileScore(item: RawOpportunity, req: ProfileRequirements): number {
  const text = `${item.title} ${item.snippet}`;
  const w = req.scoring.weights;
  const evalResult = evaluateOpportunity(item, req);
  const eligibility = evalResult.eligibility;

  const thematicRaw =
    Math.min(100, countMatches(text, req.scoring.thematic_fit_terms.high) * 35) +
    Math.min(40, countMatches(text, req.scoring.thematic_fit_terms.medium) * 12) +
    Math.min(20, countMatches(text, req.scoring.thematic_fit_terms.low) * 6);
  const thematicFit = Math.min(100, thematicRaw);
  const thematicHits =
    countMatches(text, req.scoring.thematic_fit_terms.high) + countMatches(text, req.scoring.thematic_fit_terms.medium);

  const eligibilityHits =
    countMatches(text, req.hard_filters.required_audience_any) +
    eligibility.audience_matches.length +
    eligibility.degree_level_matches.length;
  const methodologicalHits = countMatches(text, req.scoring.methodological_fit_terms);
  const resourceHits = countMatches(text, req.scoring.resource_fit_terms);

  const eligibilityFit = Math.min(100, (eligibilityHits > 0 ? 40 : 0) + eligibilityHits * 15);
  const methodologicalFit = Math.min(100, (methodologicalHits > 0 ? 30 : 0) + methodologicalHits * 18);
  const resourceFit = Math.min(100, (resourceHits > 0 ? 30 : 0) + resourceHits * 18);

  let timelineFit = 60;
  const remainingDays = daysUntil(item.date);
  if (remainingDays !== null) {
    if (remainingDays >= 90) {
      timelineFit = 85;
    } else if (remainingDays >= 21) {
      timelineFit = 100;
    } else if (remainingDays >= 10) {
      timelineFit = 70;
    } else if (remainingDays >= 0) {
      timelineFit = 30;
    } else {
      timelineFit = 0;
    }
  }

  const total = Math.round(
    thematicFit * (w.thematic_fit / 100) +
      eligibilityFit * (w.eligibility_fit / 100) +
      methodologicalFit * (w.methodological_fit / 100) +
      timelineFit * (w.timeline_fit / 100) +
      resourceFit * (w.resource_fit / 100)
  );
  const softExcludeHits = countMatches(text, req.hard_filters.soft_exclude_any ?? []);
  const softPenalty = Math.min(30, softExcludeHits * 12);
  const thematicBonus = thematicHits >= 2 ? 10 : thematicHits >= 1 ? 4 : 0;
  const hardFilterBoost = evalResult.passes_hard_filters ? 20 : 0;
  return Math.max(0, Math.min(100, total + hardFilterBoost + thematicBonus - softPenalty));
}
