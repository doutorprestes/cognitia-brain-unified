"""FINEP scraper."""
from ..shared.scraper_base import BaseScraper

class FinepScraper(BaseScraper):
    @property
    def nome(self) -> str:
        return 'FINEP'
    
    @property
    def tipo(self) -> str:
        return 'grant'
    
    def coletar(self) -> list[dict]:
        return [{'title': 'Finep Placeholder', 'url': 'https://finep.gov.br', 'source': 'FINEP', 'type': 'grant', 'snippet': ''}]
