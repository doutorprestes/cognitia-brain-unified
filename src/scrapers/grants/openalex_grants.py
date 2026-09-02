"""OpenAlex Grants scraper - API gratuita de projetos financiados."""
import httpx
from ..shared.scraper_base import BaseScraper

class OpenAlexGrantsScraper(BaseScraper):
    """Scraper para grants/funding de pesquisa via OpenAlex API."""
    
    @property
    def nome(self) -> str:
        return 'OpenAlex Grants'
    
    @property
    def tipo(self) -> str:
        return 'grant'
    
    def coletar(self) -> list[dict]:
        """Coleta grants de agências de fomento."""
        # Buscar por agências de fomento relevantes
        queries = [
            'funder.funder_type:government',
            'funder.funder_type:nonprofit',
            'funder.display_name:National Science Foundation',
            'funder.display_name:National Institutes of Health',
            'funder.display_name:European Research Council',
            'funder.display_name:Wellcome Trust',
        ]
        items = []
        for query in queries[:3]:  # Limitar para não estourar rate limit
            try:
                url = f'https://api.openalex.org/works?search={query}&per-page=10&filter=publication_year:2024-2026'
                resp = httpx.get(url, timeout=30)
                data = resp.json()
                for work in data.get('results', []):
                    title = work.get('title', '')
                    if not title:
                        continue
                    
                    # Extrair informações de funding
                    grants = work.get('grants', [])
                    if not grants:
                        continue
                    
                    for grant in grants[:1]:  # Pegar primeiro grant
                        funder = grant.get('funder_display_name', 'Unknown')
                        award_id = grant.get('award_id', '')
                        
                        # Extrair URL
                        url = ''
                        for loc in work.get('locations', []):
                            if loc.get('landing_page_url'):
                                url = loc['landing_page_url']
                                break
                        if not url:
                            url = work.get('doi', '')
                        
                        # Extrair abstract
                        abstract = ''
                        inverted = work.get('abstract_inverted_index', {})
                        if inverted:
                            word_positions = {}
                            for word, positions in inverted.items():
                                for pos in positions:
                                    word_positions[pos] = word
                            abstract = ' '.join(word_positions.get(i, '') for i in range(max(word_positions.keys()) + 1) if i in word_positions)
                        
                        items.append({
                            'title': title,
                            'url': url,
                            'source': 'OpenAlex',
                            'type': 'grant',
                            'snippet': abstract[:300] if abstract else f'Grant from {funder}',
                            'scraped_at': str(work.get('publication_date', '')),
                            'grant_info': {
                                'funder': funder,
                                'award_id': award_id
                            }
                        })
            except Exception as e:
                print(f'[OpenAlex Grants] Error: {e}')
        return items
