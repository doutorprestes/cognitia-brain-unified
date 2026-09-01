import axios from "axios";

import { FAPESP_URL } from "../config.js";
import { RawOpportunity } from "../types.js";
import { fetchWithRetry, parseGenericOpportunities } from "./common.js";

const FAPESP_SELECTORS = "article, li, .item, .opportunity, .card";
const FAPESP_KEYWORDS = /auxilio|edital|chamada|research|fellowship|bolsa|oportunidade/i;

export function parseFapespHtml(html: string): RawOpportunity[] {
  return parseGenericOpportunities(html, FAPESP_URL, {
    selectors: FAPESP_SELECTORS,
    minTitleLength: 8,
    keywords: FAPESP_KEYWORDS,
    source: "FAPESP"
  });
}

export async function fetchFapespOpportunities(): Promise<RawOpportunity[]> {
  const response = await fetchWithRetry(async () => {
    return axios.get<string>(FAPESP_URL, {
      timeout: 30000,
      headers: { "User-Agent": "grantwatch/0.1" }
    });
  });
  return parseFapespHtml(response.data);
}
