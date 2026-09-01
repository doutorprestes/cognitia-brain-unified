import * as cheerio from "cheerio";
import axios from "axios";

import { RawOpportunity } from "../types.js";
import { createLogger } from "../utils/logger.js";

const logger = createLogger("scrapers");

export function parsePtBrDate(value: string): Date | null {
  const m = value.match(/(\d{2})\/(\d{2})\/(\d{4})/);
  if (!m) {
    return null;
  }

  const date = new Date(Number(m[3]), Number(m[2]) - 1, Number(m[1]));
  return Number.isNaN(date.getTime()) ? null : date;
}

export function extractDate(text: string): string {
  const ptBr = text.match(/\b\d{2}\/\d{2}\/\d{4}\b/g);
  if (ptBr && ptBr.length > 0) {
    return ptBr[ptBr.length - 1];
  }

  const iso = text.match(/\b(\d{4})-(\d{2})-(\d{2})\b/g);
  if (iso && iso.length > 0) {
    const [year, month, day] = iso[iso.length - 1].split("-");
    return `${day}/${month}/${year}`;
  }

  return "-";
}

export function cleanText(text: string): string {
  return text.replace(/\s+/g, " ").trim();
}

export function isDeadlineInPast(date: string): boolean {
  if (date === "-") {
    return false;
  }
  const deadline = parsePtBrDate(date);
  if (!deadline) {
    return false;
  }
  const today = new Date();
  today.setHours(0, 0, 0, 0);
  return deadline < today;
}

export function firstLinkInNode($: cheerio.CheerioAPI, root: any): { title: string; link: string } | null {
  const node = $(root);
  const anchor =
    node.find("h1 > a, h2 > a, h3 > a").first().length > 0
      ? node.find("h1 > a, h2 > a, h3 > a").first()
      : node.find("a").first();
  if (!anchor.length) {
    return null;
  }

  const href = anchor.attr("href");
  if (!href) {
    return null;
  }
  return {
    title: cleanText(anchor.text()),
    link: href
  };
}

export function dedupeByKey(items: RawOpportunity[]): RawOpportunity[] {
  const seen = new Set<string>();
  const unique: RawOpportunity[] = [];
  for (const item of items) {
    const key = `${item.source ?? "?"}||${item.title}||${item.date}||${item.link}`;
    if (seen.has(key)) {
      continue;
    }
    seen.add(key);
    unique.push(item);
  }
  return unique;
}

const DEFAULT_MAX_RETRIES = 3;
const DEFAULT_BASE_DELAY_MS = 1000;
const DEFAULT_RATE_LIMIT_MS = 500;

let lastRequestTime = 0;

export async function rateLimit(delayMs: number = DEFAULT_RATE_LIMIT_MS): Promise<void> {
  const now = Date.now();
  const timeSinceLastRequest = now - lastRequestTime;
  
  if (timeSinceLastRequest < delayMs) {
    const waitTime = delayMs - timeSinceLastRequest;
    logger.debug({ waitTime }, "Rate limiting: waiting before next request");
    await new Promise((resolve) => setTimeout(resolve, waitTime));
  }
  
  lastRequestTime = Date.now();
}

export async function fetchWithRetry<T>(
  fn: () => Promise<T>,
  maxRetries: number = DEFAULT_MAX_RETRIES,
  baseDelayMs: number = DEFAULT_BASE_DELAY_MS
): Promise<T> {
  let lastError: unknown;

  for (let attempt = 0; attempt < maxRetries; attempt++) {
    try {
      return await fn();
    } catch (error) {
      lastError = error;
      const isLastAttempt = attempt === maxRetries - 1;

      if (!isLastAttempt) {
        const delayMs = baseDelayMs * Math.pow(2, attempt);
        logger.warn({ attempt: attempt + 1, maxRetries, delayMs }, "Request failed, retrying...");
        await new Promise((resolve) => setTimeout(resolve, delayMs));
      }
    }
  }

  const message = lastError instanceof Error ? lastError.message : String(lastError);
  throw new Error(`All ${maxRetries} retries failed: ${message}`);
}

export async function fetchFirstAvailableHtml(urls: readonly string[]): Promise<{ html: string; url: string }> {
  let lastError: unknown;

  for (const url of urls) {
    try {
      await rateLimit();
      const response = await fetchWithRetry(async () => {
        return axios.get<string>(url, {
          timeout: 30000,
          headers: { "User-Agent": "grantwatch/0.1" }
        });
      });
      return { html: response.data, url };
    } catch (error) {
      lastError = error;
      const message = error instanceof Error ? error.message : String(error);
      logger.warn({ url, error: message }, "Failed to fetch URL");
    }
  }

  throw lastError instanceof Error ? lastError : new Error("failed to fetch source");
}

export type GenericParserOptions = {
  selectors: string;
  minTitleLength: number;
  keywords: RegExp;
  source: string;
  maxItems?: number;
};

export function parseGenericOpportunities(
  html: string,
  baseUrl: string,
  options: GenericParserOptions
): RawOpportunity[] {
  const $ = cheerio.load(html);
  const items: RawOpportunity[] = [];
  const nodes = $(options.selectors).toArray();

  for (const nodeEl of nodes) {
    const node = $(nodeEl);
    const a = node.find("a").first();
    const href = a.attr("href");
    const title = cleanText(a.text());

    if (!href || !title || title.length < options.minTitleLength) {
      continue;
    }

    const snippet = cleanText(node.text());
    if (!options.keywords.test(snippet)) {
      continue;
    }

    const date = extractDate(`${title} ${snippet}`);
    if (isDeadlineInPast(date)) {
      continue;
    }

    const link = new URL(href, baseUrl).toString();
    items.push({
      title,
      date,
      link,
      snippet,
      source: options.source
    });
  }

  const maxItems = options.maxItems ?? 25;
  return dedupeByKey(items).slice(0, maxItems);
}
