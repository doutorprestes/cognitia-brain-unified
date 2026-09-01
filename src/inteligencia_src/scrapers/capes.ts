import { CAPES_URLS } from "../config.js";
import { RawOpportunity } from "../types.js";
import { fetchFirstAvailableHtml, parseGenericOpportunities } from "./common.js";

const CAPES_SELECTORS = "article, li, h2, h3, .item, .tileItem, .card";
const CAPES_KEYWORDS = /edital|chamada|bolsa|programa|cooperacao|fomento/i;

export function parseCapesHtml(html: string, baseUrl: string): RawOpportunity[] {
  return parseGenericOpportunities(html, baseUrl, {
    selectors: CAPES_SELECTORS,
    minTitleLength: 12,
    keywords: CAPES_KEYWORDS,
    source: "CAPES"
  });
}

export async function fetchCapesOpportunities(): Promise<RawOpportunity[]> {
  const { html, url } = await fetchFirstAvailableHtml(CAPES_URLS);
  return parseCapesHtml(html, url);
}
