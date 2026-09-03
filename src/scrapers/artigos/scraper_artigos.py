"""Scraper de artigos reais do arXiv (CS, AI, Robotics)."""
import sqlite3
import xml.etree.ElementTree as ET

import httpx


class ScraperArtigos:
    """Coleta artigos reais do arXiv nas áreas de CS, AI, Robotics."""

    HEADERS = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
    }

    CATEGORIAS = [
        "cs.AI", "cs.CL", "cs.LG", "cs.RO", "cs.MA", "stat.ML",
    ]

    def __init__(self, db_path="data/cognitia.db"):
        self.db_path = db_path

    def _get_db(self):
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _inserir(self, title, url, source, snippet="", confidence=0.9):
        conn = self._get_db()
        c = conn.cursor()
        hash_id = f"{source}:{hash(title) % 100000000}"
        try:
            c.execute(
                "INSERT INTO items (hash, title, url, source, type, snippet, confidence) VALUES (?, ?, ?, ?, 'artigo', ?, ?)",
                (hash_id, title, url, source, snippet, confidence)
            )
            conn.commit()
            conn.close()
            return True
        except sqlite3.IntegrityError:
            conn.close()
            return False

    def scrape_arxiv(self, categoria, max_results=25):
        url = f"https://export.arxiv.org/api/query?search_query=cat:{categoria}&sortBy=submittedDate&max_results={max_results}"
        total = 0
        try:
            r = httpx.get(url, headers=self.HEADERS, timeout=20, follow_redirects=True)
            if r.status_code != 200:
                return 0
            root = ET.fromstring(r.text)
            ns = {"atom": "http://www.w3.org/2005/Atom"}
            for entry in root.findall("atom:entry", ns):
                title = entry.find("atom:title", ns)
                if title is None or not title.text:
                    continue
                title = title.text.strip().replace("\n", " ")
                link = entry.find("atom:id", ns)
                if link is None:
                    continue
                link = link.text.strip()
                summary = entry.find("atom:summary", ns)
                snippet = summary.text.strip()[:300] if summary is not None and summary.text else ""
                if self._inserir(title, link, "arXiv", snippet):
                    total += 1
        except Exception as e:
            print(f"  arXiv {categoria}: {e}")
        return total

    def coletar_tudo(self):
        print("=== COLETA DE ARTIGOS ===")
        total = 0
        for cat in self.CATEGORIAS:
            print(f"\n{cat}...")
            t = self.scrape_arxiv(cat, 20)
            print(f"   {t} artigos coletados")
            total += t
        print(f"\n=== TOTAL: {total} novos artigos ===")
        return total


if __name__ == "__main__":
    s = ScraperArtigos()
    s.coletar_tudo()
