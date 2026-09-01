"""Scout - busca web automatizada."""
import logging
from typing import Optional

import httpx
from bs4 import BeautifulSoup

from ..shared.config import config

logger = logging.getLogger(__name__)

class WebScout:
    """Busca web automatizada por palavras-chave."""
    
    def __init__(self):
        self.client = httpx.Client(timeout=30)
    
    def buscar(self, query: str, max_results: int = 10) -> list:
        """Busca web por query."""
        items = []
        try:
            url = f'https://html.duckduckgo.com/html/?q={query}'
            resp = self.client.get(url)
            soup = BeautifulSoup(resp.content, 'html.parser')
            
            for result in soup.find_all('a', {'class': 'result__a'}):
                title = result.get_text(strip=True)
                href = result.get('href', '')
                if title and href:
                    items.append({
                        'title': title,
                        'url': href,
                        'source': 'Web',
                        'type': 'artigo',
                        'snippet': ''
                    })
                    if len(items) >= max_results:
                        break
        except Exception as e:
            print(f'[Scout] Error: {e}')
        return items
