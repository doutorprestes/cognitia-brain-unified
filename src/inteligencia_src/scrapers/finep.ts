import axios from "axios";
import * as cheerio from "cheerio";

import { FINEP_URL } from "../config.js";
import { RawOpportunity } from "../types.js";
import { cleanText, dedupeByKey, extractDate, fetchWithRetry, firstLinkInNode, isDeadlineInPast } from "./common.js";

export function parseFinepHtml(html: string): RawOpportunity[] {
  const $ = cheerio.load(html);
  const cards = $("#conteudoChamada .item").toArray();

  const items: RawOpportunity[] = [];
  for (const card of cards) {
    const parsedLink = firstLinkInNode($, card);
    if (!parsedLink) {
      continue;
    }

    const title = parsedLink.title;
    const link = new URL(parsedLink.link, FINEP_URL).toString();
    const node = $(card);

    const snippet =
      cleanText(node.find("div.prazo_div").first().text()) ||
      cleanText(node.find("div.prazo").first().text()) ||
      cleanText(node.text());

    const date = extractDate(snippet);
    if (isDeadlineInPast(date)) {
      continue;
    }

    items.push({
      title,
      date,
      link,
      snippet,
      source: "FINEP"
    });
  }

  return dedupeByKey(items);
}

export async function fetchFinepOpportunities(): Promise<RawOpportunity[]> {
  const response = await fetchWithRetry(async () => {
    return axios.get<string>(FINEP_URL, {
      timeout: 30000,
      headers: { "User-Agent": "grantwatch/0.1" }
    });
  });
  return parseFinepHtml(response.data);
}
