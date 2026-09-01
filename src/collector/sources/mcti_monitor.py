"""IA Brasil — Coletor para o painel de monitoramento oficial do MCTI.

Coleta dados do painel de monitoramento do PBIA no site do MCTI,
que mostra o status de execução das 54 ações estruturantes.

Fonte oficial: https://www.gov.br/mcti/pt-br/acompanhe-o-mcti/transformacaodigital/plano-brasileiro-de-inteligencia-artificial

Uso:
    from src.collector.sources.mcti_monitor import MCTIMonitorCollector

    collector = MCTIMonitorCollector()
    results = await collector.collect()
"""

from __future__ import annotations

import re
from datetime import UTC, datetime
from typing import Any

from loguru import logger

from src.collector.core.fetcher import HTTPFetcher
from src.collector.core.provenance import ProvenanceTracker

# URLs do painel de monitoramento do MCTI
MCTI_PANEL_URLS = [
    "https://www.gov.br/mcti/pt-br/acompanhe-o-mcti/transformacaodigital/plano-brasileiro-de-inteligencia-artificial",
    "https://www.gov.br/mcti/pt-br/acompanhe-o-mcti/noticias/2025/11/grupo-de-trabalho-do-pbia-lanca-painel-de-monitoramento-de-acoes",
]

# Status possíveis no painel oficial
STATUS_MAP = {
    "entregue": "entregue",
    "concluído": "entregue",
    "concluido": "entregue",
    "entregas": "entregue",
    "em andamento": "em_andamento",
    "em_execução": "em_andamento",
    "em_execucao": "em_andamento",
    "iniciado": "em_andamento",
    "em preparação": "nao_iniciado",
    "em_preparacao": "nao_iniciado",
    "não iniciado": "nao_iniciado",
    "nao_iniciado": "nao_iniciado",
}


class MCTIMonitorCollector:
    """Coletor para o painel de monitoramento oficial do MCTI.

    Coleta informações sobre o status de execução das ações do PBIA
    a partir da página oficial do MCTI.

    Attributes:
        fetcher: Instância do HTTPFetcher para requisições
        provenance: Instância do ProvenanceTracker
    """

    # Versão do parser/coletor (registrada no IngestionRun — issue #1087).
    PARSER_VERSION = "2.0.0"

    def __init__(self) -> None:
        self.fetcher = HTTPFetcher(rate_limit=1, cache_ttl=3600)
        self.provenance = ProvenanceTracker()

    async def collect(self) -> list[dict[str, Any]]:
        """Coleta dados do painel de monitoramento do MCTI.

        Processa todas as URLs configuradas — não interrompe na primeira
        URL que retorne itens.

        Returns:
            Lista de evidências padronizadas com status das ações.
        """
        evidence_items: list[dict[str, Any]] = []

        try:
            await self.fetcher.initialize()
            for url in MCTI_PANEL_URLS:
                try:
                    response = await self.fetcher.fetch(url, use_cache=False)

                    if response.status != 200:
                        logger.warning(f"MCTI monitor returned status {response.status} for {url}")
                        continue

                    html = response.data if isinstance(response.data, str) else ""
                    items = self._parse_panel(html, url)
                    evidence_items.extend(items)

                    self.provenance.add_record(
                        url=url,
                        method="GET",
                        confidence=0.85,
                        metadata={
                            "source": "mcti_monitor",
                            "items_found": len(items),
                        },
                    )

                    logger.info(f"MCTI monitor: {len(items)} items from {url}")

                except Exception as e:
                    logger.warning(f"MCTI monitor fetch failed for {url}: {e}")
        finally:
            await self.fetcher.close()

        return evidence_items

    def _parse_panel(self, html: str, source_url: str) -> list[dict[str, Any]]:
        """Parse the HTML panel to extract action delivery statuses.

        The MCTI panel contains information about which of the 54 structural
        actions have been delivered, are in progress, or are in preparation.

        O resumo do painel só é gerado quando ao menos uma métrica é
        encontrada no HTML; caso contrário retorna lista vazia (abstenção).

        Args:
            html: Raw HTML content from the MCTI page
            source_url: Source URL for provenance

        Returns:
            List of standardized evidence dicts
        """
        evidence_items: list[dict[str, Any]] = []
        now = datetime.now(UTC).isoformat()

        # Extract key statistics from the page
        delivered_match = re.search(
            r"(\d+)\s*(?:já\s+)?(?:estão?\s+com\s+entrega|apresentaram\s+entregas?|entregues?)",
            html,
            re.IGNORECASE,
        )
        initiated_match = re.search(
            r"(\d+)\s*(?:já\s+)?(?:foram?\s+iniciadas?|em\s+(?:andamento|execução|execucao))",
            html,
            re.IGNORECASE,
        )
        preparation_match = re.search(
            r"(\d+)\s*(?:em\s+)?(?:preparação|preparacao|preparo)",
            html,
            re.IGNORECASE,
        )

        # Extract total actions count
        total_match = re.search(r"(\d+)\s*ações?\s*estruturantes?", html, re.IGNORECASE)

        financial_match = re.search(
            r"R\$\s*([\d.,]+)\s*(bilhões?|milhões?|mil)",
            html,
            re.IGNORECASE,
        )

        # Extract percentages
        pct_delivered_match = re.search(
            r"([\d.,]+)%\s*(?:das\s+ações?\s+)?(?:entregues?|com\s+entrega)",
            html,
            re.IGNORECASE,
        )

        # O resumo do painel só é gerado quando ao menos uma métrica é
        # efetivamente encontrada no HTML. Sem métricas, retornamos dados
        # vazios (abstenção) em vez de fabricar um resumo com valores 0.
        metrics_found = any(
            match is not None
            for match in (
                delivered_match,
                initiated_match,
                preparation_match,
                financial_match,
                pct_delivered_match,
            )
        )

        if not metrics_found:
            return evidence_items

        total_actions = int(total_match.group(1)) if total_match else 54
        delivered_count = int(delivered_match.group(1)) if delivered_match else 0
        initiated_count = int(initiated_match.group(1)) if initiated_match else 0
        preparation_count = int(preparation_match.group(1)) if preparation_match else 0

        financial_value = None
        if financial_match:
            value_str = financial_match.group(1).replace(".", "").replace(",", ".")
            multiplier = financial_match.group(2).lower()
            if "bilh" in multiplier:
                financial_value = float(value_str) * 1_000_000_000
            elif "milh" in multiplier:
                financial_value = float(value_str) * 1_000_000
            elif "mil" in multiplier:
                financial_value = float(value_str) * 1_000

        pct_delivered = None
        if pct_delivered_match:
            raw = pct_delivered_match.group(1).replace(",", ".")
            pct_delivered = float(raw)

        # Create evidence for the overall PBIA status
        summary_text = (
            f"Painel oficial do MCTI: {delivered_count} de {total_actions} ações estruturantes "
            f"com entrega, {initiated_count} iniciadas"
        )
        if preparation_count > 0:
            summary_text += f", {preparation_count} em preparação"
        if financial_value:
            summary_text += f". R$ {financial_value:,.0f} em recursos utilizados"

        evidence_items.append(
            {
                "titulo": "Painel de Monitoramento do PBIA - MCTI",
                "descricao": summary_text,
                "data": now,
                "fonte_url": source_url,
                "tipo": "relatorio",
                "confianca": 0.9,
                "metadata": {
                    "total_acoes": total_actions,
                    "entregues": delivered_count,
                    "iniciadas": initiated_count,
                    "em_preparacao": preparation_count,
                    "valor_utilizado": financial_value,
                    "pct_entregues": pct_delivered,
                    "fonte": "painel_oficial_mcti",
                },
            }
        )

        # Extract individual action mentions if available
        # Look for patterns like "Ação 1: ..." or "Ação de impacto N: ..."
        action_pattern = re.compile(
            r"(?:Ação|acao)\s+(?:de\s+impacto\s+)?(\d+|[IVX]+):\s*(.+?)(?:\.|$)",
            re.IGNORECASE | re.MULTILINE,
        )
        for match in action_pattern.finditer(html):
            action_num = match.group(1)
            action_desc = match.group(2).strip()[:200]

            evidence_items.append(
                {
                    "titulo": f"Ação PBIA {action_num}: {action_desc[:50]}",
                    "descricao": action_desc,
                    "data": now,
                    "fonte_url": source_url,
                    "tipo": "ato_oficial",
                    "confianca": 0.8,
                    "metadata": {
                        "acao_codigo": action_num,
                        "fonte": "painel_oficial_mcti",
                    },
                }
            )

        return evidence_items

    async def get_provenance_records(self) -> list[dict[str, Any]]:
        """Retorna os registros de proveniência."""
        records = self.provenance.get_records()
        return [record.model_dump() for record in records]

    async def close(self) -> None:
        """Limpa recursos do fetcher."""
        await self.fetcher.close()
