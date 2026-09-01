"""Base scraper interface."""
from abc import ABC, abstractmethod

class BaseScraper(ABC):
    @abstractmethod
    def coletar(self) -> list[dict]:
        """Coleta itens da fonte."""
        pass
    
    @property
    @abstractmethod
    def nome(self) -> str:
        """Nome da fonte."""
        pass
    
    @property
    @abstractmethod
    def tipo(self) -> str:
        """Tipo: 'grant' ou 'artigo'."""
        pass
