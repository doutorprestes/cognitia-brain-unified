import { EligibilityAssessment, RawOpportunity } from "../types.js";

function normalize(text: string): string {
  return text
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "")
    .toLowerCase();
}

const DEGREE_TERMS = ["mestrado", "master", "msc", "phd", "doctoral", "postdoctoral", "studentship"];
const AUDIENCE_TERMS = [
  "student",
  "estudante",
  "researcher",
  "pesquisador",
  "early career",
  "graduate",
  "postgraduate",
  "ict",
  "university",
  "universidade"
];
const INSTITUTION_TERMS = ["university", "universidade", "institute", "instituto", "higher education", "research organisation", "ict"];
const VISA_TERMS = ["eu nationals", "citizen", "residency", "visa", "international students", "open to international applicants"];

function findMatches(text: string, terms: readonly string[]): string[] {
  const t = normalize(text);
  return terms.filter((term) => {
    const normalizedTerm = normalize(term);
    if (normalizedTerm.length <= 3) {
      const pattern = new RegExp(`(^|\\W)${normalizedTerm.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")}(\\W|$)`);
      return pattern.test(t);
    }
    return t.includes(normalizedTerm);
  });
}

export function extractEligibilityAssessment(item: RawOpportunity): EligibilityAssessment {
  const blob = `${item.title} ${item.snippet} ${item.raw_audience ?? ""}`;

  const audienceMatches = findMatches(blob, AUDIENCE_TERMS);
  const degreeMatches = findMatches(blob, DEGREE_TERMS);
  const institutionMatches = findMatches(blob, INSTITUTION_TERMS);
  const visaMatches = findMatches(blob, VISA_TERMS);

  const confidence = Math.min(
    100,
    audienceMatches.length * 20 + degreeMatches.length * 20 + institutionMatches.length * 15 + (visaMatches.length > 0 ? 10 : 0)
  );

  const parts = [
    audienceMatches.length > 0 ? `audiencia: ${audienceMatches.join(", ")}` : "",
    degreeMatches.length > 0 ? `nivel: ${degreeMatches.join(", ")}` : "",
    institutionMatches.length > 0 ? `instituicao: ${institutionMatches.join(", ")}` : "",
    visaMatches.length > 0 ? `mobilidade: ${visaMatches.join(", ")}` : ""
  ].filter(Boolean);

  return {
    audience_matches: audienceMatches,
    degree_level_matches: degreeMatches,
    institution_matches: institutionMatches,
    visa_or_nationality_notes: visaMatches,
    confidence,
    summary: parts.length > 0 ? parts.join(" | ") : "elegibilidade pouco explicita no texto coletado"
  };
}
