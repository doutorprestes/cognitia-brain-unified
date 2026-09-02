"""Testes unitários para scrapers."""
import pytest
from src.scrapers.artigos.arxiv import ArxivScraper
from src.scrapers.artigos.openalex import OpenAlexScraper
from src.scrapers.grants.openalex_grants import GrantsScraper


def test_arxiv_scraper():
    """Testa scraper arXiv."""
    scraper = ArxivScraper()
    items = scraper.coletar()
    assert isinstance(items, list)
    assert scraper.nome == 'arXiv'
    assert scraper.tipo == 'artigo'
    if items:
        assert 'title' in items[0]
        assert 'url' in items[0]
        assert 'source' in items[0]


def test_openalex_scraper():
    """Testa scraper OpenAlex."""
    scraper = OpenAlexScraper()
    items = scraper.coletar()
    assert isinstance(items, list)
    assert scraper.nome == 'OpenAlex'
    assert scraper.tipo == 'artigo'


def test_grants_scraper():
    """Testa scraper Grants."""
    scraper = GrantsScraper()
    items = scraper.coletar()
    assert isinstance(items, list)
    assert scraper.nome == 'OpenAlex Grants'
    assert scraper.tipo == 'grant'


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
