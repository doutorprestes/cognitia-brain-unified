"""DOU (Diário Oficial da União) scraper."""
import httpx
from bs4 import BeautifulSoup
from ..shared.scraper_base import BaseScraper

class DouScraper(BaseScraper):
    @property
    def nome(self) -> str:
        return 'DOU'
    
    @property
    def tipo(self) -> str:
        return 'grant'
    
    def coletar(self) -> list[dict]:
        url = 'https://www.in.gov.br/web/dou/-/buscar/-/1?query=edital+chamada+publica'
        items = []
        try:
            resp = httpx.get(url, timeout=30)
            soup = BeautifulSoup(resp.content, 'html.parser')
            for link in soup.find_all('a', href=True):
                title = link.get_text(strip=True)
                href = link.get('href', '')
                if not title or len(title) < 10:
                    continue
                if 'edital' in title.lower() or 'chamada' in title.lower():
                    items.append({'title': title[:120], 'url': href, 'source': 'DOU', 'type': 'grant', 'snippet': ''})
        except Exception as e:
            print(f'[DOU] Error: {e}')
        return items
