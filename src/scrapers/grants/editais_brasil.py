"""Editais Brasil scraper - coleta manual de editais de fomento."""
import httpx
from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright
from ..shared.scraper_base import BaseScraper


class EditaisBrasilScraper(BaseScraper):
    """Scraper para editais de fomento brasileiros (FAPESP, CNPq, CAPES, FINEP)."""
    
    @property
    def nome(self) -> str:
        return 'Editais Brasil'
    
    @property
    def tipo(self) -> str:
        return 'grant'
    
    def coletar(self) -> list[dict]:
        """Coleta editais de agências brasileiras."""
        items = []
        
        # FAPESP
        items.extend(self._fapesp())
        
        # CNPq
        items.extend(self._cnpq())
        
        # CAPES
        items.extend(self._capes())
        
        # FINEP
        items.extend(self._finep())
        
        return items
    
    def _fapesp(self) -> list[dict]:
        """FAPESP - Fundação de Amparo à Pesquisa do Estado de São Paulo."""
        items = []
        try:
            # FAPESP não permite acesso direto, usar página de auxílios
            url = 'https://fapesp.br/auxilios'
            with sync_playwright() as p:
                browser = p.chromium.launch(headless=True)
                page = browser.new_page()
                page.goto(url, timeout=60000)
                page.wait_for_timeout(5000)
                html = page.content()
                browser.close()
            
            soup = BeautifulSoup(html, 'html.parser')
            for link in soup.find_all('a', href=True):
                title = link.get_text(strip=True)
                href = link.get('href', '')
                if not title or len(title) < 15:
                    continue
                if 'edital' in title.lower() or 'chamada' in title.lower() or 'bolsa' in title.lower():
                    if href and not href.startswith('http'):
                        href = f'https://fapesp.br{href}'
                    items.append({
                        'title': title[:120],
                        'url': href,
                        'source': 'FAPESP',
                        'type': 'grant',
                        'snippet': 'Edital FAPESP de fomento à pesquisa.'
                    })
        except Exception as e:
            print(f'[FAPESP] Error: {e}')
        return items
    
    def _cnpq(self) -> list[dict]:
        """CNPq - Conselho Nacional de Desenvolvimento Científico e Tecnológico."""
        items = []
        try:
            url = 'https://www.gov.br/cnpq/pt-br/assuntos/chamadas-publicas'
            resp = httpx.get(url, timeout=30)
            soup = BeautifulSoup(resp.content, 'html.parser')
            for link in soup.find_all('a', href=True):
                title = link.get_text(strip=True)
                href = link.get('href', '')
                if not title or len(title) < 15:
                    continue
                if 'edital' in title.lower() or 'chamada' in title.lower():
                    if href and not href.startswith('http'):
                        href = f'https://www.gov.br{href}'
                    items.append({
                        'title': title[:120],
                        'url': href,
                        'source': 'CNPq',
                        'type': 'grant',
                        'snippet': 'Chamada pública CNPq.'
                    })
        except Exception as e:
            print(f'[CNPq] Error: {e}')
        return items
    
    def _capes(self) -> list[dict]:
        """CAPES - Coordenação de Aperfeiçoamento de Pessoal de Nível Superior."""
        items = []
        try:
            url = 'https://www.gov.br/capes/pt-br/acesso-a-informacao/acoes-e-programas/bolsas'
            resp = httpx.get(url, timeout=30)
            soup = BeautifulSoup(resp.content, 'html.parser')
            for link in soup.find_all('a', href=True):
                title = link.get_text(strip=True)
                href = link.get('href', '')
                if not title or len(title) < 15:
                    continue
                if 'edital' in title.lower() or 'programa' in title.lower() or 'bolsa' in title.lower():
                    if href and not href.startswith('http'):
                        href = f'https://www.gov.br{href}'
                    items.append({
                        'title': title[:120],
                        'url': href,
                        'source': 'CAPES',
                        'type': 'grant',
                        'snippet': 'Programa de bolsas CAPES.'
                    })
        except Exception as e:
            print(f'[CAPES] Error: {e}')
        return items
    
    def _finep(self) -> list[dict]:
        """FINEP - Financiadora de Estudos e Projetos."""
        items = []
        try:
            url = 'https://www.finep.gov.br/chamadas-publicas'
            resp = httpx.get(url, timeout=30)
            soup = BeautifulSoup(resp.content, 'html.parser')
            for h2 in soup.find_all('h2'):
                title = h2.get_text(strip=True)
                if not title or len(title) < 10:
                    continue
                parent = h2.find_parent('a') or h2.find_next('a')
                href = parent.get('href', '') if parent else ''
                if href and not href.startswith('http'):
                    href = f'https://www.finep.gov.br{href}'
                items.append({
                    'title': title[:120],
                    'url': href,
                    'source': 'FINEP',
                    'type': 'grant',
                    'snippet': 'Chamada pública FINEP para inovação.'
                })
        except Exception as e:
            print(f'[FINEP] Error: {e}')
        return items
