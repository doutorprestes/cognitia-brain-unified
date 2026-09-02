"""CAPES scraper refinado - so editais de IA/tech."""
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
                    
                    # Filtra por palavras-chave relevantes
                    palavras_chave = [
                        'inteligencia artificial', 'ia', 'machine learning', 'deep learning',
                        'robotica', 'robot', 'automacao', 'industria 4.0', 'iot',
                        'inovacao', 'tecnologia', 'digital', 'transformacao digital',
                        'ciencia de dados', 'big data', 'computacao', 'software',
                        'hardware', 'eletronica', 'telecomunicacoes', '5g',
                        'saude', 'educacao', 'sustentabilidade', 'energia',
                        'edital', 'chamada', 'bolsa', 'auxilio', 'pesquisa'
                    ]
                    
                    text_lower = text.lower()
                    if not any(kw in text_lower for kw in palavras_chave):
                        continue
                    
                    # Filtrar lixo
                    termos_excluir = ['alteracao', 'resultado', 'errata', 'retificacao',
                                      'anexo', 'modelo', 'formato', 'lista', 'relacao',
                                      'portaria', 'regulamento', '2009', '2013', '2016', '2018']
                    if any(te in text_lower for te in termos_excluir):
                        continue
                    
                    if href and not href.startswith('http'):
                        href = urljoin('https://www.gov.br', href)
                    items.append({'title': text[:120], 'url': href, 'source': 'CAPES', 'type': 'grant', 'snippet': ''})
            except Exception as e:
                print(f'[CAPES] Error: {e}')
        return items
