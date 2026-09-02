import httpx
from bs4 import BeautifulSoup
from ..shared.scraper_base import BaseScraper

class ArxivScraper(BaseScraper):
    @property
    def nome(self) -> str:
        return 'arXiv'
    
    @property
    def tipo(self) -> str:
        return 'artigo'
    
    def coletar(self) -> list[dict]:
        queries = [
            'cat:cs.RO AND (robot OR robotics OR humanoid OR swarm)',
            'cat:cs.MA AND (multi-agent OR collective OR cooperative)',
            'cat:cs.AI AND (alignment OR interpretability OR ethics)',
            'cat:cs.CL AND (language model OR LLM OR introspection)',
        ]
        items = []
        for query in queries:
            try:
                url = f'https://export.arxiv.org/api/query?search_query={query}&start=0&max_results=5&sortBy=submittedDate&sortOrder=descending'
                resp = httpx.get(url, timeout=30, follow_redirects=True)
                soup = BeautifulSoup(resp.content, 'xml')
                for entry in soup.find_all('entry')[:5]:
                    title = entry.find('title')
                    link = entry.find('link', {'type': 'text/html'})
                    summary = entry.find('summary')
                    published = entry.find('published')
                    if title and link:
                        items.append({
                            'title': title.get_text(strip=True),
                            'url': link.get('href', ''),
                            'source': 'arXiv',
                            'type': 'artigo',
                            'snippet': summary.get_text(strip=True)[:300] if summary else '',
                            'scraped_at': published.get_text(strip=True) if published else ''
                        })
            except Exception as e:
                print(f'[arXiv] Error: {e}')
        return items
