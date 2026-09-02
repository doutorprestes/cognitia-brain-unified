"""Base scraper class."""

class BaseScraper:
    """Base class for all scrapers."""
    
    @property
    def nome(self) -> str:
        raise NotImplementedError
    
    @property
    def tipo(self) -> str:
        raise NotImplementedError
    
    def coletar(self) -> list[dict]:
        raise NotImplementedError
