"""arXiv scraper."""
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
        url = 'http://export.arxiv.org/api/query?search_query=cat:cs.AI&start=0&max_results=10'
        items = []
        try:
            resp = httpx.get(url, timeout=30)
            soup = BeautifulSoup(resp.content, 'xml')
            for entry in soup.find_all('entry'):
                title = entry.find('title')
                link = entry.find('link', {'type': 'text/html'})
                if title and link:
                    items.append({
                        'title': title.get_text(strip=True),
                        'url': link.get('href', ''),
                        'source': 'arXiv',
                        'type': 'artigo',
                        'snippet': ''
                    })
        except Exception as e:
            print(f'[arXiv] Error: {e}')
        return items
