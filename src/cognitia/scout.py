"""Módulo de Scout (Olheiro) para buscar conteúdos relevantes na Web."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

import feedparser
from pyalex import Works
from pyalex import config as pyalex_config
import requests
import time

from cognitia_brain.config import Config

logger = logging.getLogger(__name__)
# Identificação polida para o OpenAlex
pyalex_config.email = "cognitia-brain-local@localhost.local"

class WebScout:
    def __init__(self, config: Config) -> None:
        self.config = config
        self.history_path = config.acervo_dir.parent / ".chromadb" / "scout_history.json"
        self.seen_urls, self.findings = self._load_history()
        
        self.keywords = config.scout_keywords or []
        self.rss_feeds = config.scout_rss_feeds or []

    def _load_history(self) -> tuple[set[str], list[dict[str, Any]]]:
        if self.history_path.exists():
            try:
                data = json.loads(self.history_path.read_text(encoding="utf-8"))
                if isinstance(data, dict):
                    seen = set(data.get("seen_urls", []))
                    findings = data.get("findings", [])
                    return seen, findings
                elif isinstance(data, list):
                    # Formato antigo era apenas uma lista de seen_urls
                    return set(data), []
            except Exception:
                pass
        return set(), []

    def _save_history(self, new_findings: list[dict[str, Any]]) -> None:
        try:
            from datetime import datetime
            self.history_path.parent.mkdir(parents=True, exist_ok=True)
            
            # Formatar novos findings
            formatted_new = []
            for f in new_findings:
                formatted_new.append({
                    "title": f.get("title") or "Sem título",
                    "summary": f.get("summary") or f.get("abstract") or f.get("excerpt") or "",
                    "source": f.get("source") or "",
                    "link": f.get("url") or f.get("link") or "",
                    "date": datetime.now().strftime("%Y-%m-%d %H:%M")
                })
            
            # Junta com os anteriores
            all_findings = self.findings + formatted_new
            # Limita tamanho do histórico
            all_findings = all_findings[-200:]
            
            data = {
                "seen_urls": list(self.seen_urls),
                "findings": all_findings
            }
            self.history_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
            self.findings = all_findings
        except Exception as e:
            logger.error(f"Erro ao salvar histórico do scout: {e}")

    def search_openalex(self) -> list[dict[str, Any]]:
        """Busca no OpenAlex acadêmico pelas palavras-chave."""
        results = []
        for kw in self.keywords:
            try:
                logger.info(f"Scout OpenAlex: buscando '{kw}'...")
                works = Works().search(kw).sort(publication_date="desc").get(per_page=2)
                for w in works:
                    url = w.get("doi") or w.get("id")
                    if url and url not in self.seen_urls:
                        # Extrai o abstract que no OpenAlex às vezes vem invertido
                        abstr = w.get("abstract") or ""
                        results.append({
                            "title": w.get("title", "Sem título"),
                            "url": url,
                            "abstract": abstr,
                            "source": "OpenAlex Acadêmico"
                        })
                        self.seen_urls.add(url)
            except Exception as e:
                logger.error(f"Erro no OpenAlex ({kw}): {e}")
        return results

    def search_rss(self) -> list[dict[str, Any]]:
        """Busca em feeds RSS/Atom."""
        results = []
        for feed_url in self.rss_feeds:
            try:
                logger.info(f"Scout RSS: lendo '{feed_url}'...")
                parsed = feedparser.parse(feed_url)
                # Pega as 2 entradas mais recentes
                for entry in parsed.entries[:2]:
                    url = entry.link
                    if url and url not in self.seen_urls:
                        results.append({
                            "title": entry.title,
                            "url": url,
                            "abstract": entry.get("summary", ""),
                            "source": f"RSS ({parsed.feed.get('title', feed_url)})"
                        })
                        self.seen_urls.add(url)
            except Exception as e:
                logger.error(f"Erro no RSS ({feed_url}): {e}")
        return results

    def search_arxiv(self) -> list[dict[str, Any]]:
        """Busca na API do arXiv por palavra-chave (alternativa ao OpenAlex).

        Usa export.arxiv.org/api/query — estável, sem autenticação.
        """
        import urllib.parse

        results = []
        for kw in self.keywords:
            try:
                logger.info(f"Scout arXiv: buscando '{kw}'...")
                query = urllib.parse.quote(kw)
                url = (
                    "http://export.arxiv.org/api/query?search_query=all:"
                    f"{query}&sortBy=submittedDate&sortOrder=descending"
                    "&max_results=2"
                )
                resp = requests.get(url, timeout=20)
                resp.raise_for_status()
                parsed = feedparser.parse(resp.text)
                for entry in parsed.entries:
                    link = entry.get("link")
                    if link and link not in self.seen_urls:
                        summary = entry.get("summary", "")
                        results.append({
                            "title": entry.get("title", "Sem título").strip(),
                            "url": link,
                            "abstract": summary,
                            "source": "arXiv",
                        })
                        self.seen_urls.add(link)
            except Exception as e:
                logger.error(f"Erro no arXiv ({kw}): {e}")
        return results

    def search_semantic_scholar(self) -> list[dict[str, Any]]:
        """Busca no Semantic Scholar por palavra-chave (alternativa ao OpenAlex).

        API pública, estável, retorna abstract. Limite de rate (sem chave).
        """
        results = []
        for kw in self.keywords:
            try:
                logger.info(f"Scout Semantic Scholar: buscando '{kw}'...")
                url = "https://api.semanticscholar.org/graph/v1/paper/search"
                params = {
                    "query": kw,
                    "fields": "title,url,abstract,externalIds",
                    "limit": 2,
                    "sort": "publicationDate:desc",
                }
                resp = requests.get(url, params=params, timeout=20)
                resp.raise_for_status()
                data = resp.json()
                for paper in data.get("data", []):
                    link = paper.get("url") or (
                        paper.get("externalIds", {}).get("DOI")
                    )
                    if link and link not in self.seen_urls:
                        results.append({
                            "title": paper.get("title", "Sem título"),
                            "url": link,
                            "abstract": paper.get("abstract", ""),
                            "source": "Semantic Scholar",
                        })
                        self.seen_urls.add(link)
            except Exception as e:
                logger.error(f"Erro no Semantic Scholar ({kw}): {e}")
            # Respeita rate limit da API pública (sem chave: ~1 req/seg)
            time.sleep(3)
        return results

    def run_scout(self) -> list[dict[str, Any]]:
        """Roda todas as buscas e retorna os achados inéditos."""
        all_results = []
        all_results.extend(self.search_openalex())
        all_results.extend(self.search_arxiv())
        all_results.extend(self.search_semantic_scholar())
        all_results.extend(self.search_rss())

        if all_results:
            self._save_history(all_results)

        return all_results
