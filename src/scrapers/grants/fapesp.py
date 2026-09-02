"""FAPESP scraper - parser específico de editais."""
import httpx
from bs4 import BeautifulSoup
from ..shared.scraper_base import BaseScraper

class FapespScraper(BaseScraper):
    @property
    def nome(self) -> str:
        return 'FAPESP'
    
    @property
    def tipo(self) -> str:
        return 'grant'
    
    def coletar(self) -> list[dict]:
        urls = [
            'https://fapesp.br/auxilios',
            'https://fapesp.br/bolsas',
            'https://fapesp.br/chamadas',
        ]
        items = []
        for url in urls:
            try:
                resp = httpx.get(url, timeout=30)
                soup = BeautifulSoup(resp.content, 'html.parser')
                
                # Buscar links de editais/chamadas
                for link in soup.find_all('a', href=True):
                    title = link.get_text(strip=True)
                    href = link.get('href', '')
                    
                    if not title or len(title) < 15:
                        continue
                    
                    # Filtrar por palavras-chave relevantes
                    title_lower = title.lower()
                    keywords = ['edital', 'chamada', 'bolsa', 'auxílio', 'pesquisa', 'inovação', 
                               'tecnologia', 'ia', 'inteligência artificial', 'robot', 'machine learning',
                               'deep learning', 'computação', 'engenharia', 'saúde', 'educação']
                    
                    if not any(kw in title_lower for kw in keywords):
                        continue
                    
                    # Filtrar lixo
                    exclude = ['resultado', 'errata', 'retificação', 'alteração', 'anexo', 
                              'modelo', 'formato', 'lista', 'relação', 'portaria', 'regulamento',
                              '2009', '2013', '2016', '2018', '2019', '2020', '2021', '2022', '2023']
                    if any(ex in title_lower for ex in exclude):
                        continue
                    
                    if href and not href.startswith('http'):
                        href = f'https://fapesp.br{href}'
                    
                    items.append({
                        'title': title[:120],
                        'url': href,
                        'source': 'FAPESP',
                        'type': 'grant',
                        'snippet': ''
                    })
            except Exception as e:
                print(f'[FAPESP] Error: {e}')
        return items
