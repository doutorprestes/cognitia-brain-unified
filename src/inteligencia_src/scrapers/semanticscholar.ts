/**
 * Semantic Scholar API Scraper
 * 
 * Busca artigos recentes do Semantic Scholar por tópicos
 * do projeto de mestrado (MARL, Robótica, Deep RL).
 * 
 * API: https://api.semanticscholar.org/
 */

import { logger } from '../utils/logger.js';
import type { ScrapedItem, ScraperConfig, RawOpportunity } from '../types.js';

const S2_API = 'https://api.semanticscholar.org/graph/v1';

const SEARCH_FIELDS = [
  'title',
  'abstract',
  'year',
  'authors',
  'externalIds',
  'url',
  'publicationVenue',
  'citationCount',
  'tldr',
].join(',');

const DEFAULT_TOPICS = [
  'multi-agent reinforcement learning',
  'swarm robotics coordination',
  'deep reinforcement learning robotics',
  'autonomous multi-agent systems',
];

export async function scrapeSemanticScholar(
  config: ScraperConfig = {}
): Promise<RawOpportunity[]> {
  const topics = config.topics || DEFAULT_TOPICS;
  const limit = config.limit || 10;

  const items: ScrapedItem[] = [];

  for (const topic of topics) {
    const url = `${S2_API}/paper/search?query=${encodeURIComponent(topic)}&limit=${limit}&fields=${SEARCH_FIELDS}&sort=publicationDate:desc`;

    try {
      logger.info(`[SemanticScholar] Buscando: "${topic}"`);
      const response = await fetch(url, {
        headers: { Accept: 'application/json' },
        signal: AbortSignal.timeout(15000),
      });

      if (!response.ok) {
        logger.warn(`[SemanticScholar] HTTP ${response.status} para "${topic}"`);
        continue;
      }

      const data = await response.json();
      const papers = data.data || [];

      for (const paper of papers) {
        const doi = paper.externalIds?.DOI;
        const arxivId = paper.externalIds?.ArXiv;
        const s2Url = paper.url || (doi ? `https://doi.org/${doi}` : undefined);

        items.push({
          id: `s2:${paper.paperId}`,
          source: 'semanticscholar',
          title: paper.title || '',
          summary: paper.abstract || paper.tldr?.text || '',
          url: s2Url || `https://api.semanticscholar.org/CorpusID:${paper.corpusId}`,
          authors: paper.authors?.map((a: any) => a.name).join(', ') || '',
          publishedDate: paper.year?.toString() || '',
          venue: paper.publicationVenue?.name || '',
          citationCount: paper.citationCount || 0,
          type: 'paper',
        });
      }

      logger.info(`[SemanticScholar] "${topic}": ${papers.length} resultados`);
    } catch (err: any) {
      logger.error(`[SemanticScholar] Erro em "${topic}": ${err.message}`);
    }
  }

  // Map ScrapedItem → RawOpportunity para compatibilidade com o pipeline
  return items.map((item) => ({
    title: item.title,
    date: item.publishedDate 
      ? `${item.publishedDate}-01-01` 
      : new Date().toISOString().split('T')[0],
    link: item.url,
    snippet: item.summary,
    source: 'Semantic Scholar',
    opportunity_type: 'scholarship' as const,
    raw_audience: item.authors || '',
    funding_amount: '',
  }));
}
