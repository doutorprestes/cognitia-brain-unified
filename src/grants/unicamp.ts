import axios from "axios";
import * as cheerio from "cheerio";

import { UNICAMP_URLS } from "../config.js";
import { RawOpportunity } from "../types.js";
import { cleanText, dedupeByKey, fetchWithRetry, isDeadlineInPast } from "./common.js";

const GRANT_OFFICE_URL = UNICAMP_URLS[0];
const FAEPEX_URL = UNICAMP_URLS[1];

function extractLastPtBrDate(text: string): string {
  const matches = [...text.matchAll(/\b\d{2}\/\d{2}\/\d{4}\b/g)];
  return matches.length > 0 ? matches[matches.length - 1][0] : "-";
}

function isPrimaryCallLink(text: string): boolean {
  return /chamada|edital/i.test(text) && !/resultado|webinar|faq|anexo|planilha|formulario|vídeo|video/i.test(text);
}

export function parseUnicampGrantOfficeHtml(html: string): RawOpportunity[] {
  const $ = cheerio.load(html);
  const items: RawOpportunity[] = [];

  $(".filtrable-item").each((_, el) => {
    const root = $(el);
    const title = cleanText(root.find(".edital__title").first().text());
    if (!title) {
      return;
    }

    const author = cleanText(root.find(".edital__author").first().text());
    const time = cleanText(root.find(".edital__time").first().text());
    const snippet = cleanText(`${author}. ${time}. ${root.text()}`);
    const date = extractLastPtBrDate(time || snippet);
    if (isDeadlineInPast(date)) {
      return;
    }

    const callLink = root
      .find("a.edital__file__link")
      .toArray()
      .map((a) => ({ text: cleanText($(a).text()), href: $(a).attr("href") }))
      .find((link) => link.href && isPrimaryCallLink(link.text));

    const link = callLink?.href ? new URL(callLink.href, GRANT_OFFICE_URL).toString() : GRANT_OFFICE_URL;
    items.push({
      title,
      date,
      link,
      snippet,
      source: "Unicamp/PRP"
    });
  });

  return dedupeByKey(items);
}

export function parseUnicampFaepexHtml(html: string): RawOpportunity[] {
  const $ = cheerio.load(html);
  const items: RawOpportunity[] = [];

  $(".filtrable-item").each((_, el) => {
    const root = $(el);
    const title = cleanText(root.find(".edital__title").first().text());
    if (!title) {
      return;
    }

    const year = cleanText(root.find(".edital__number").first().text());
    const time = cleanText(root.find(".edital__time").first().text());
    const snippet = cleanText(`${year}. ${time}. ${root.text()}`);
    const date = extractLastPtBrDate(time || snippet);
    if (isDeadlineInPast(date)) {
      return;
    }

    const callLink = root
      .find("a.edital__file__link")
      .toArray()
      .map((a) => ({ text: cleanText($(a).text()), href: $(a).attr("href") }))
      .find((link) => link.href && isPrimaryCallLink(link.text));

    const link = callLink?.href ? new URL(callLink.href, FAEPEX_URL).toString() : FAEPEX_URL;
    items.push({
      title,
      date,
      link,
      snippet,
      source: "Unicamp/FAEPEX"
    });
  });

  return dedupeByKey(items);
}

export async function fetchUnicampOpportunities(): Promise<RawOpportunity[]> {
  const [grantOffice, faepex] = await Promise.all([
    fetchWithRetry(async () => axios.get<string>(GRANT_OFFICE_URL, {
      timeout: 30000,
      headers: { "User-Agent": "grantwatch/0.1" }
    })),
    fetchWithRetry(async () => axios.get<string>(FAEPEX_URL, {
      timeout: 30000,
      headers: { "User-Agent": "grantwatch/0.1" }
    }))
  ]);

  return dedupeByKey([
    ...parseUnicampGrantOfficeHtml(grantOffice.data),
    ...parseUnicampFaepexHtml(faepex.data)
  ]);
}
