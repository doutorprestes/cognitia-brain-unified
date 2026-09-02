"""OpenAlex scraper - API gratuita de artigos acadêmicos sem rate limit agressivo."""
import httpx
from ..shared.scraper_base import BaseScraper

class OpenAlexScraper(BaseScraper):
    @property
    def nome(self) -> str:
        return 'OpenAlex'
    
    @property
    def tipo(self) -> str:
        return 'artigo'
    
    def coletar(self) -> list[dict]:
        queries = [
            'multi-agent-reinforcement-learning',
            'large-language-models-alignment',
            'humanoid-robotics-locomotion',
            'collective-learning-swarm',
            'ai-governance-ethics-interpretability',
            'prompt-injection-adversarial',
        ]
        items = []
        for query in queries:
            try:
                url = f'https://api.openalex.org/works?search={query}&per-page=5&filter=publication_year:2025-2026'
                resp = httpx.get(url, timeout=30)
                data = resp.json()
                for work in data.get('results', []):
                    title = work.get('title', '')
                    if not title:
                        continue
                    
                    # Extrair URL
                    url = ''
                    for loc in work.get('locations', []):
                        if loc.get('landing_page_url'):
                            url = loc['landing_page_url']
                            break
                    if not url:
                        url = work.get('doi', '')
                    
                    # Extrair abstract (invertido)
                    abstract = ''
                    inverted = work.get('abstract_inverted_index', {})
                    if inverted:
                        # Reconstruir abstract do inverted index
                        word_positions = {}
                        for word, positions in inverted.items():
                            for pos in positions:
                                word_positions[pos] = word
                        abstract = ' '.join(word_positions.get(i, '') for i in range(max(word_positions.keys()) + 1) if i in word_positions)
                    
                    # Extrair venue/source
                    venue = ''
                    for loc in work.get('locations', []):
                        source = loc.get('source', {})
                        if source:
                            venue = source.get('display_name', '')
                            break
                    
                    items.append({
                        'title': title,
                        'url': url,
                        'source': venue or 'OpenAlex',
                        'type': 'artigo',
                        'snippet': abstract[:300] if abstract else '',
                        'scraped_at': str(work.get('publication_date', ''))
                    })
            except Exception as e:
                print(f'[OpenAlex] Error: {e}')
        return items
