"""Scraper de editais reais de agências brasileiras de fomento."""
import sqlite3
from urllib.parse import urljoin

import httpx
from bs4 import BeautifulSoup


class ScraperEditais:
    """Coleta editais de FAPESP, CNPq, CAPES e FINEP."""

    HEADERS = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
    }

    def __init__(self, db_path="data/cognitia.db"):
        self.db_path = db_path

    def _get_db(self):
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _inserir(self, title, url, source, snippet="", confidence=0.8):
        conn = self._get_db()
        c = conn.cursor()
        hash_id = f"{source}:{hash(title) % 100000000}"
        try:
            c.execute(
                "INSERT INTO items (hash, title, url, source, type, snippet, confidence) VALUES (?, ?, ?, ?, 'grant', ?, ?)",
                (hash_id, title, url, source, snippet, confidence)
            )
            conn.commit()
            conn.close()
            return True
        except sqlite3.IntegrityError:
            conn.close()
            return False

    def scrape_fapesp(self):
        """FAPESP - Auxílios e bolsas."""
        base = "https://fapesp.br"
        urls = [f"{base}/bolsas", f"{base}/auxilios", f"{base}/chamadas"]
        total = 0
        for url in urls:
            try:
                r = httpx.get(url, headers=self.HEADERS, timeout=15)
                if r.status_code != 200:
                    continue
                soup = BeautifulSoup(r.text, "html.parser")
                for a in soup.find_all("a", href=True):
                    href = a["href"]
                    text = a.get_text(strip=True)
                    if len(text) < 20 or len(text) > 200:
                        continue
                    if any(k in href.lower() for k in ["bolsa", "auxilio", "chamada", "edital"]):
                        full_url = urljoin(base, href)
                        if self._inserir(text, full_url, "FAPESP", text[:200]):
                            total += 1
            except Exception as e:
                print(f"  FAPESP {url}: {e}")
        return total

    def scrape_cnpq(self):
        """CNPq - Bolsas e auxílios."""
        urls = ["https://cnpq.br/bolsas", "https://cnpq.br/chamadas-publicas"]
        total = 0
        for url in urls:
            try:
                r = httpx.get(url, headers=self.HEADERS, timeout=15, follow_redirects=True)
                if r.status_code != 200:
                    continue
                soup = BeautifulSoup(r.text, "html.parser")
                for a in soup.find_all("a", href=True):
                    text = a.get_text(strip=True)
                    if len(text) < 15 or len(text) > 200:
                        continue
                    if any(k in text.lower() for k in ["bolsa", "auxílio", "chamada", "edital"]):
                        full_url = urljoin("https://cnpq.br", a["href"])
                        if self._inserir(text, full_url, "CNPq", text[:200]):
                            total += 1
            except Exception as e:
                print(f"  CNPq {url}: {e}")
        return total

    def scrape_capes(self):
        """CAPES - Bolsas e programas."""
        urls = ["https://capes.gov.br/bolsas", "https://capes.gov.br/chamadas-publicas"]
        total = 0
        for url in urls:
            try:
                r = httpx.get(url, headers=self.HEADERS, timeout=15, follow_redirects=True)
                if r.status_code != 200:
                    continue
                soup = BeautifulSoup(r.text, "html.parser")
                for a in soup.find_all("a", href=True):
                    text = a.get_text(strip=True)
                    if len(text) < 15 or len(text) > 200:
                        continue
                    if any(k in text.lower() for k in ["bolsa", "programa", "chamada", "edital"]):
                        full_url = urljoin("https://capes.gov.br", a["href"])
                        if self._inserir(text, full_url, "CAPES", text[:200]):
                            total += 1
            except Exception as e:
                print(f"  CAPES {url}: {e}")
        return total

    def scrape_finep(self):
        """FINEP - Financiamento e subvenção."""
        urls = ["https://www.finep.gov.br/chamadas-publicas", "https://www.finep.gov.br/apoio-a-projetos"]
        total = 0
        for url in urls:
            try:
                r = httpx.get(url, headers=self.HEADERS, timeout=15, follow_redirects=True)
                if r.status_code != 200:
                    continue
                soup = BeautifulSoup(r.text, "html.parser")
                for a in soup.find_all("a", href=True):
                    text = a.get_text(strip=True)
                    if len(text) < 15 or len(text) > 200:
                        continue
                    if any(k in text.lower() for k in ["chamada", "edital", "financiamento", "subvenção"]):
                        full_url = urljoin("https://www.finep.gov.br", a["href"])
                        if self._inserir(text, full_url, "FINEP", text[:200]):
                            total += 1
            except Exception as e:
                print(f"  FINEP {url}: {e}")
        return total

    def coletar_tudo(self):
        print("=== COLETA DE EDITAIS ===")
        total = 0
        print("\n1. FAPESP...")
        t = self.scrape_fapesp()
        print(f"   {t} editais coletados")
        total += t
        print("\n2. CNPq...")
        t = self.scrape_cnpq()
        print(f"   {t} editais coletados")
        total += t
        print("\n3. CAPES...")
        t = self.scrape_capes()
        print(f"   {t} editais coletados")
        total += t
        print("\n4. FINEP...")
        t = self.scrape_finep()
        print(f"   {t} editais coletados")
        total += t
        print(f"\n=== TOTAL: {total} novos itens ===")
        return total


if __name__ == "__main__":
    s = ScraperEditais()
    s.coletar_tudo()
