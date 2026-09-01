"""CAPES scraper."""
from urllib.parse import urljoin
from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright
from ..shared.scraper_base import BaseScraper

class CapesScraper(BaseScraper):
    @property
    def nome(self) -> str:
        return 'CAPES'
    
    @property
    def tipo(self) -> str:
        return 'grant'
    
    def coletar(self) -> list[dict]:
        urls = [
            'https://www.gov.br/capes/pt-br/acesso-a-informacao/acoes-e-programas/bolsas/bolsas-e-auxilios-internacionais/encontre-aqui/paises/multinacional/programa-de-doutorado-sanduiche-no-exterior-pdse',
            'https://www.gov.br/capes/pt-br/acesso-a-informacao/acoes-e-programas/bolsas/bolsas-e-auxilios-internacionais/encontre-aqui/paises/multinacional/programa-de-estudantes-convenio-de-pos-graduacao-pec-pg',
        ]
        items = []
        for url in urls:
            try:
                with sync_playwright() as p:
                    browser = p.chromium.launch(headless=True)
                    page = browser.new_page()
                    page.goto(url, timeout=60000)
                    page.wait_for_timeout(5000)
                    html = page.content()
                    browser.close()
                
                soup = BeautifulSoup(html, 'html.parser')
                for link in soup.find_all('a', href=True):
                    text = link.get_text(strip=True)
                    href = link.get('href', '')
                    if not text or len(text) < 10:
                        continue
                    if any(k in text.lower() for k in ['edital', 'resultado', 'anexo', 'portaria']):
                        if href and not href.startswith('http'):
                            href = urljoin('https://www.gov.br', href)
                        items.append({'title': text[:120], 'url': href, 'source': 'CAPES', 'type': 'grant', 'snippet': ''})
            except Exception as e:
                print(f'[CAPES] Error: {e}')
        return items
