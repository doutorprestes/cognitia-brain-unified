/**
 * arXiv API Scraper
 * 
 * Busca artigos recentes do arXiv por categorias e palavras-chave
 * configuradas para o projeto de mestrado (MARL, Robótica).
 * 
 * API: https://arxiv.org/help/api
 */

import { logger } from '../utils/logger.js';
import type { ScrapedItem, ScraperConfig, RawOpportunity } from '../types.js';

const ARXIV_API = 'http://export.arxiv.org/api/query';

const DEFAULT_CATEGORIES = [
  'cs.MA',   // Multiagent Systems
  'cs.RO',   // Robotics
  'cs.AI',   // Artificial Intelligence
  'cs.LG',   // Machine Learning
  'stat.ML', // Machine Learning (Statistics)
];

const DEFAULT_KEYWORDS = [
  'multi-agent reinforcement learning',
  'swarm robotics',
  'autonomous multi-agent systems',
  'deep reinforcement learning',
  'multi-robot coordination',
];

const MAX_RESULTS_PER_KEYWORD = 5;

export async function scrapeArxiv(
  config: ScraperConfig = {}
): Promise<RawOpportunity[]> {
  const categories = config.categories || DEFAULT_CATEGORIES;
  const keywords = config.keywords || DEFAULT_KEYWORDS;
  const maxResults = config.maxResults || 20;
  const daysBack = config.daysBack || 3;

  const items: ScrapedItem[] = [];

  for (const keyword of keywords.slice(0, 3)) {
    const query = `search_query=all:${encodeURIComponent(keyword)}&start=0&max_results=${maxResults}&sortBy=submittedDate&sortOrder=descending`;
    const url = `${ARXIV_API}?${query}`;

    try {
      logger.info(`[arXiv] Buscando: "${keyword}"`);
      const response = await fetch(url, { signal: AbortSignal.timeout(15000) });
      const xml = await response.text();

      // Parse XML entries
      const entryRegex = /<entry>([\s\S]*?)<\/entry>/g;
      let match;
      while ((match = entryRegex.exec(xml)) !== null) {
        const entry = match[1];
        const title = extractTag(entry, 'title')?.replace(/\s+/g, ' ').trim();
        const summary = extractTag(entry, 'summary')?.replace(/\s+/g, ' ').trim();
        const link = extractTag(entry, 'id')?.trim();
        const published = extractTag(entry, 'published')?.trim();
        const authors = [...entry.matchAll(/<author>[\s\S]*?<name>(.*?)<\/name>[\s\S]*?<\/author>/g)]
          .map(m => m[1])
          .join(', ');
        const pdfLink = link?.replace('/abs/', '/pdf/') + '.pdf';
        const category = extractTag(entry, 'arxiv:primary_category')?.match(/term="([^"]+)"/)?.[1];

        if (title && link) {
          items.push({
            id: `arxiv:${link.split('/').pop()}`,
            source: 'arxiv',
            title,
            summary: summary || '',
            url: link,
            pdfUrl: pdfLink,
            authors,
            publishedDate: published || '',
            category: category || '',
            type: 'paper',
            rawData: { keyword, xml: entry.substring(0, 500) },
          });
        }
      }
      logger.info(`[arXiv] "${keyword}": ${items.length} resultados`);
    } catch (err: any) {
      logger.error(`[arXiv] Erro em "${keyword}": ${err.message}`);
    }
  }

  // Map ScrapedItem → RawOpportunity para compatibilidade com o pipeline
  return items.map((item) => ({
    title: item.title,
    date: item.publishedDate || new Date().toISOString().split('T')[0],
    link: item.url,
    snippet: item.summary,
    source: 'arXiv',
    opportunity_type: 'scholarship' as const,
    raw_audience: item.authors || '',
    funding_amount: '',
  }));
}

function extractTag(xml: string, tag: string): string | null {
  const match = xml.match(new RegExp(`<${tag}[^>]*>([\\s\\S]*?)<\/${tag}>`));
  return match ? match[1].trim() : null;
}
