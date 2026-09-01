import { CNPQ_URLS } from "../config.js";
import { RawOpportunity } from "../types.js";
import { fetchFirstAvailableHtml, parseGenericOpportunities } from "./common.js";

const CNPQ_SELECTORS = "article, li, h2, h3, .item, .tileItem, .card";
const CNPQ_KEYWORDS = /edital|chamada|programa|bolsa|fomento/i;

export function parseCnpqHtml(html: string, baseUrl: string): RawOpportunity[] {
  return parseGenericOpportunities(html, baseUrl, {
    selectors: CNPQ_SELECTORS,
    minTitleLength: 12,
    keywords: CNPQ_KEYWORDS,
    source: "CNPq"
  });
}

export async function fetchCnpqOpportunities(): Promise<RawOpportunity[]> {
  const { html, url } = await fetchFirstAvailableHtml(CNPQ_URLS);
  return parseCnpqHtml(html, url);
}
