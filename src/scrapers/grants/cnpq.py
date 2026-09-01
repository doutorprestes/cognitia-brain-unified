"""CNPq scraper."""
from urllib.parse import urljoin
from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright
from ..shared.scraper_base import BaseScraper

class CnpqScraper(BaseScraper):
    @property
    def nome(self) -> str:
        return 'CNPq'
    
    @property
    def tipo(self) -> str:
        return 'grant'
    
    def coletar(self) -> list[dict]:
        url = 'https://www.gov.br/cnpq/pt-br/assuntos/chamadas-publicas'
        items = []
        try:
            with sync_playwright() as p:
                browser = p.chromium.launch(headless=True)
                page = browser.new_page()
                page.goto(url, timeout=60000)
                page.wait_for_timeout(5000)
                html = page.content()
                browser.close()
            
            soup = BeautifulSoup(html, 'html.parser')
            for link in soup.select("a[href*='chamada'], a[href*='edital']"):
                title = link.get_text(strip=True)
                href = link.get('href', '')
                if not title or len(title) < 10:
                    continue
                if href and not href.startswith('http'):
                    href = urljoin('https://www.gov.br', href)
                items.append({'title': title, 'url': href, 'source': 'CNPq', 'type': 'grant', 'snippet': ''})
        except Exception as e:
            print(f'[CNPq] Error: {e}')
        return items
