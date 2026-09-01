"""arXiv scraper."""
from ..shared.scraper_base import BaseScraper

class ArxivScraper(BaseScraper):
    @property
    def nome(self) -> str:
        return 'arXiv'
    
    @property
    def tipo(self) -> str:
        return 'artigo'
    
    def coletar(self) -> list[dict]:
        return [{'title': 'arXiv Placeholder', 'url': 'https://arxiv.org', 'source': 'arXiv', 'type': 'artigo', 'snippet': ''}]
