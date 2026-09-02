"""Semantic Scholar scraper - API gratuita de artigos acadêmicos."""
import httpx
from ..shared.scraper_base import BaseScraper

class SemanticScholarScraper(BaseScraper):
    @property
    def nome(self) -> str:
        return 'Semantic Scholar'
    
    @property
    def tipo(self) -> str:
        return 'artigo'
    
    def coletar(self) -> list[dict]:
        queries = [
            'multi-agent reinforcement learning robotics',
            'large language model alignment safety',
            'humanoid robot locomotion manipulation',
            'collective learning swarm robotics',
            'AI governance ethics interpretability',
        ]
        items = []
        for query in queries:
            try:
                url = f'https://api.semanticscholar.org/graph/v1/paper/search?query={query}&limit=5&fields=title,abstract,url,year,venue&year=2025-2026'
                resp = httpx.get(url, timeout=30)
                data = resp.json()
                for paper in data.get('data', []):
                    title = paper.get('title', '')
                    abstract = paper.get('abstract', '') or ''
                    url = paper.get('url', '')
                    year = paper.get('year', '')
                    venue = paper.get('venue', '')
                    
                    if title and url:
                        items.append({
                            'title': title,
                            'url': url,
                            'source': venue or 'Semantic Scholar',
                            'type': 'artigo',
                            'snippet': abstract[:300] if abstract else '',
                            'scraped_at': f'{year}-01-01' if year else ''
                        })
            except Exception as e:
                print(f'[Semantic Scholar] Error: {e}')
        return items
