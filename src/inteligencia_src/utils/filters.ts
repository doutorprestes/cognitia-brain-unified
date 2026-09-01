export const GLOBAL_REJECT_TERMS = [
  "credenciamento",
  "resultado final",
  "errata",
  "retificacao",
  "chamada encerrada",
  "encerrada"
];

export const INTERNATIONAL_REJECT_TERMS = [
  "law enforcement",
  "corrections",
  "reentry",
  "crime",
  "offender",
  "policing",
  "humanities",
  "uk registered organisations",
  "uk registered organization",
  "uk-based",
  "based in the uk",
  "united kingdom only",
  "u.s. mission to argentina",
  "argentina",
  "u.s. citizens only",
  "us citizens only",
  "united states citizens only"
];

export const BRAZIL_LOCATION_ACCEPT_TERMS = [
  "campinas",
  "unicamp",
  "sao paulo",
  "são paulo",
  "sp, brazil",
  "sp, brasil",
  "brazil",
  "brasil",
  "brazilian",
  "brasileiro",
  "brasileira",
  "brasileiros",
  "brasileiras",
  "latin america",
  "america latina",
  "américa latina",
  "remote",
  "online",
  "worldwide",
  "global",
  "any nationality",
  "all nationalities",
  "international applicants",
  "international candidates",
  "open to applicants from any country"
];

export const ALL_REJECT_TERMS = [...GLOBAL_REJECT_TERMS, ...INTERNATIONAL_REJECT_TERMS];

export function matchesAnyTerm(text: string, terms: readonly string[]): boolean {
  const normalized = text.toLowerCase();
  return terms.some((term) => normalized.includes(term.toLowerCase()));
}

export function matchesAllTerms(text: string, terms: readonly string[]): boolean {
  const normalized = text.toLowerCase();
  return terms.every((term) => normalized.includes(term.toLowerCase()));
}

export function acceptsBrazilCampinasApplicant(item: { source?: string; title: string; snippet: string; raw_audience?: string }): boolean {
  const source = item.source ?? "";
  const sourceLower = source.toLowerCase();

  if (!["ukri", "grantsgov", "euraxess"].includes(sourceLower)) {
    return true;
  }

  const text = `${item.title} ${item.snippet} ${item.raw_audience ?? ""}`;
  if (matchesAnyTerm(text, INTERNATIONAL_REJECT_TERMS)) {
    return false;
  }

  return matchesAnyTerm(text, BRAZIL_LOCATION_ACCEPT_TERMS);
}
