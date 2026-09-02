"""FINEP scraper refinado - so editais de IA/tech."""
from urllib.parse import urljoin
from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright
from ..shared.scraper_base import BaseScraper

class FinepScraper(BaseScraper):
    @property
    def nome(self) -> str:
        return 'FINEP'
    
    @property
    def tipo(self) -> str:
        return 'grant'
    
    def coletar(self) -> list[dict]:
        url = 'https://www.finep.gov.br/chamadas-publicas'
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
            for h2 in soup.find_all('h2'):
                title = h2.get_text(strip=True)
                if not title or len(title) < 10:
                    continue
                
                # Filtra por palavras-chave relevantes
                palavras_chave = [
                    'inteligencia artificial', 'ia', 'machine learning', 'deep learning',
                    'robotica', 'robot', 'automacao', 'industria 4.0', 'iot',
                    'inovacao', 'tecnologia', 'digital', 'transformacao digital',
                    'ciencia de dados', 'big data', 'computacao', 'software',
                    'hardware', 'eletronica', 'telecomunicacoes', '5g',
                    'saude', 'educacao', 'sustentabilidade', 'energia'
                ]
                
                title_lower = title.lower()
                if not any(kw in title_lower for kw in palavras_chave):
                    continue
                
                # Filtrar lixo
                termos_excluir = ['alteracao', 'resultado', 'errata', 'retificacao',
                                  'anexo', 'modelo', 'formato', 'lista', 'relacao',
                                  'portaria', 'regulamento', '2009', '2013', '2016', '2018']
                if any(te in title_lower for te in termos_excluir):
                    continue
                
                parent = h2.find_parent('a') or h2.find_next('a')
                href = parent.get('href', '') if parent else ''
                if href and not href.startswith('http'):
                    href = urljoin('https://www.finep.gov.br', href)
                
                items.append({
                    'title': title[:120],
                    'url': href,
                    'source': 'FINEP',
                    'type': 'grant',
                    'snippet': ''
                })
        except Exception as e:
            print(f'[FINEP] Error: {e}')
        return items
