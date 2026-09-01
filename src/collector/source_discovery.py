"""IA Brasil — Source Discovery.

Scanner semanal que detecta novas fontes governamentais relevantes
e notifica para aprovação manual.

Roda todo domingo às 2h via APScheduler.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import datetime

import httpx
from loguru import logger

from src.modules.collector.config import load_sources

# Keywords para busca de relevância
RELEVANCE_KEYWORDS = [
    "inteligência artificial",
    "plano brasileiro de ia",
    "pbia",
    "governança de ia",
    "regulação de ia",
    "pl 2338",
    "ética em ia",
    "ia responsável",
]

# Órgãos prioritários (score alto)
PRIORITY_ORGANS = [
    "mcti",
    "cgee",
    "cnpq",
    "finep",
    "fapesp",
    "aneel",
    "cgu",
    "tcu",
    "anpd",
]


@dataclass
class SourceCandidate:
    """Candidato a nova fonte de dados."""

    url: str
    title: str
    source_type: str  # "ckan_dataset", "gov_page", "api", "report"
    organ: str | None
    relevance_score: float  # 0.0 a 1.0
    detection_date: str
    keywords_matched: list[str]


class SourceDiscovery:
    """Detecta novas fontes governamentais relevantes."""

    def __init__(self) -> None:
        self.existing_urls: set[str] = set()
        self._load_existing_urls()

    def _load_existing_urls(self) -> None:
        """Carrega URLs já cadastradas em sources.yaml."""
        try:
            sources = load_sources()
            for source in sources:
                if source.url:
                    self.existing_urls.add(source.url.rstrip("/"))
        except Exception:
            logger.warning("[Discovery] Não foi possível carregar sources.yaml")

    async def scan_dados_gov_br(self) -> list[SourceCandidate]:
        """Busca novos datasets em dados.gov.br relevantes para IA/PBIA."""
        candidates: list[SourceCandidate] = []
        api_key = os.getenv("DADOS_GOV_API_KEY")

        if not api_key:
            logger.warning("[Discovery] DADOS_GOV_API_KEY não configurada — skip dados.gov.br")
            return candidates

        try:
            async with httpx.AsyncClient(timeout=30) as client:
                for keyword in ["inteligência artificial", "PBIA", "plano IA"]:
                    response = await client.get(
                        "https://dados.gov.br/api/3/action/package_search",
                        params={"q": keyword, "rows": 20},
                        headers={"Authorization": api_key},
                    )

                    if response.status_code != 200:
                        continue

                    data = response.json()
                    results = data.get("result", {}).get("results", [])

                    for item in results:
                        url = item.get("url", "")
                        title = item.get("title", "")
                        org = item.get("organization", {}).get("name", "")

                        # Pular se já existe
                        if url.rstrip("/") in self.existing_urls:
                            continue

                        # Calcular score de relevância
                        score = self._calculate_relevance(title, org, keyword)

                        if score >= 0.6:
                            candidates.append(
                                SourceCandidate(
                                    url=url,
                                    title=title,
                                    source_type="ckan_dataset",
                                    organ=org,
                                    relevance_score=score,
                                    detection_date=datetime.now().isoformat(),
                                    keywords_matched=[keyword],
                                )
                            )

        except Exception as e:
            logger.error(f"[Discovery] Erro ao scanear dados.gov.br: {e}")

        return candidates

    async def scan_gov_br_mcti(self) -> list[SourceCandidate]:
        """Busca novas páginas em gov.br/mcti relacionadas a IA."""
        candidates: list[SourceCandidate] = []

        try:
            async with httpx.AsyncClient(timeout=30) as client:
                response = await client.get(
                    "https://www.gov.br/mcti/pt-br/acompanhe-o-mcti/transformacaodigital",
                )

                if response.status_code != 200:
                    return candidates

                # Buscar links que contenham keywords relevantes
                from bs4 import BeautifulSoup

                soup = BeautifulSoup(response.text, "lxml")
                links = soup.find_all("a", href=True)

                for link in links:
                    href = link.get("href", "")
                    text = link.get_text(strip=True).lower()

                    # Filtrar links internos do MCTI
                    if not isinstance(href, str) or not href.startswith("https://www.gov.br/mcti"):
                        continue

                    # Pular se já existe
                    if href.rstrip("/") in self.existing_urls:
                        continue

                    # Calcular relevância
                    score = self._calculate_relevance(text, "mcti", "")

                    if score >= 0.5:
                        candidates.append(
                            SourceCandidate(
                                url=str(href),
                                title=link.get_text(strip=True),
                                source_type="gov_page",
                                organ="mcti",
                                relevance_score=score,
                                detection_date=datetime.now().isoformat(),
                                keywords_matched=[],
                            )
                        )

        except Exception as e:
            logger.error(f"[Discovery] Erro ao scanear gov.br/mcti: {e}")

        return candidates

    def _calculate_relevance(self, title: str, organ: str, search_keyword: str) -> float:
        """Calcula score de relevância (0.0 a 1.0)."""
        score = 0.0
        title_lower = title.lower()
        organ_lower = organ.lower()

        # Match de keywords no título
        for kw in RELEVANCE_KEYWORDS:
            if kw.lower() in title_lower:
                score += 0.3
                break

        # Órgão prioritário
        for priority_organ in PRIORITY_ORGANS:
            if priority_organ in organ_lower:
                score += 0.3
                break

        # Keyword de busca
        if search_keyword and search_keyword.lower() in title_lower:
            score += 0.2

        # Tipo de conteúdo relevante
        relevant_terms = [
            "relatório",
            "indicador",
            "meta",
            "plano",
            "programa",
            "dados",
            "dashboard",
            "monitoramento",
        ]
        for term in relevant_terms:
            if term in title_lower:
                score += 0.1
                break

        return min(score, 1.0)

    async def run_weekly_scan(self) -> list[SourceCandidate]:
        """Executa scan semanal de novas fontes."""
        logger.info("[Discovery] Iniciando scan semanal de novas fontes")

        all_candidates: list[SourceCandidate] = []

        # Scan dados.gov.br
        dados_candidates = await self.scan_dados_gov_br()
        all_candidates.extend(dados_candidates)
        logger.info(f"[Discovery] dados.gov.br: {len(dados_candidates)} candidatos")

        # Scan gov.br/mcti
        mcti_candidates = await self.scan_gov_br_mcti()
        all_candidates.extend(mcti_candidates)
        logger.info(f"[Discovery] gov.br/mcti: {len(mcti_candidates)} candidatos")

        # Deduplicar por URL
        seen_urls: set[str] = set()
        unique_candidates: list[SourceCandidate] = []
        for candidate in all_candidates:
            if candidate.url not in seen_urls:
                seen_urls.add(candidate.url)
                unique_candidates.append(candidate)

        # Ordenar por relevância
        unique_candidates.sort(key=lambda c: c.relevance_score, reverse=True)

        logger.info(
            f"[Discovery] Total: {len(unique_candidates)} candidatos únicos (threshold: 0.6)"
        )

        # Notificar via Telegram
        if unique_candidates:
            await self._notify_candidates(unique_candidates)

        return unique_candidates

    async def _notify_candidates(self, candidates: list[SourceCandidate]) -> None:
        """Envia notificação Telegram com candidatos encontrados."""
        token = os.getenv("TELEGRAM_BOT_TOKEN")
        chat_id = os.getenv("TELEGRAM_CHAT_ID")
        if not token or not chat_id:
            return

        message = "🔍 Novas fontes detectadas:\n\n"

        for i, candidate in enumerate(candidates[:5], 1):  # Top 5
            score_pct = int(candidate.relevance_score * 100)
            message += (
                f"{i}. {candidate.title[:60]}\n"
                f"   URL: {candidate.url[:80]}\n"
                f"   Tipo: {candidate.source_type}\n"
                f"   Confiança: {score_pct}%\n\n"
            )

        if len(candidates) > 5:
            message += f"... e mais {len(candidates) - 5} candidatos\n\n"

        message += (
            "Para aprovar, use:\n  /approve <url>\nOu adicione manualmente em config/sources.yaml"
        )

        try:
            async with httpx.AsyncClient() as client:
                await client.post(
                    f"https://api.telegram.org/bot{token}/sendMessage",
                    json={
                        "chat_id": chat_id,
                        "text": message,
                        "parse_mode": "HTML",
                    },
                    timeout=10,
                )
        except Exception:
            pass
