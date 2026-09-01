"""IA Brasil — Scraper para o dashboard Power BI do PBIA/CGEE.

Utiliza Playwright para acessar o dashboard Power BI em
https://pbia.cgee.org.br/resultados e extrair dados de acompanhamento.

Requisitos:
    pip install playwright
    playwright install chromium

Uso:
    from src.collector.sources.pbia_powerbi import PBIAPowerBIScraper

    scraper = PBIAPowerBIScraper()
    results = await scraper.collect()
    await scraper.close()
"""

from __future__ import annotations

import base64
from datetime import UTC, datetime
from typing import Any

from loguru import logger

from src.collector.core.provenance import ProvenanceTracker

# URL do dashboard Power BI do PBIA
PBIA_POWERBI_URL = "https://pbia.cgee.org.br/resultados"


class PBIAPowerBIScraper:
    """Scraper para o dashboard Power BI do PBIA usando Playwright.

    Acessa o dashboard Power BI publicado pelo CGEE e extrai
    dados de acompanhamento das ações do PBIA.

    Attributes:
        dashboard_url: URL do dashboard Power BI
        provenance: Instância do ProvenanceTracker
    """

    def __init__(self) -> None:
        self.dashboard_url = PBIA_POWERBI_URL
        self.provenance = ProvenanceTracker()
        self._playwright: Any = None
        self._browser: Any = None

    async def _ensure_browser(self) -> bool:
        """Lazy-init Playwright browser.

        Returns:
            True if browser is available, False otherwise.
        """
        try:
            from playwright.async_api import async_playwright

            if not self._playwright:
                self._playwright = await async_playwright().start()
                self._browser = await self._playwright.chromium.launch(headless=True)
                logger.info("Playwright browser initialized for Power BI scraping")
            return True
        except ImportError:
            logger.warning(
                "Playwright not installed. Install with: "
                "pip install playwright && playwright install chromium"
            )
            return False
        except Exception as e:
            logger.warning(f"Failed to initialize Playwright: {e}")
            return False

    async def collect(self) -> list[dict[str, Any]]:
        """Scrape the Power BI dashboard for PBIA data.

        Returns:
            List of standardized evidence dicts with dashboard data.
        """
        if not await self._ensure_browser():
            return []

        evidence_items: list[dict[str, Any]] = []
        now = datetime.now(UTC).isoformat()

        try:
            page = await self._browser.new_page()

            # Navigate to the dashboard with timeout
            logger.info(f"Navigating to Power BI dashboard: {self.dashboard_url}")
            await page.goto(self.dashboard_url, wait_until="networkidle", timeout=60000)

            # Wait for Power BI content to load (iframes)
            await page.wait_for_timeout(5000)

            # Try to extract data from the page
            # Power BI embedded reports render in iframes
            frames = page.frames
            logger.info(f"Found {len(frames)} frames on page")

            for frame in frames:
                try:
                    # Look for data tables or key metrics
                    content = await frame.content()
                    if not content:
                        continue

                    # Extract text content that might contain status data
                    text_content = await frame.evaluate("""
                        () => {
                            const elements = document.querySelectorAll(
                                '[class*="card"], [class*="metric"], [class*="kpi"], ' +
                                '[class*="value"], [class*="title"], table, h1, h2, h3'
                            );
                            return Array.from(elements).map(el => ({
                                tag: el.tagName,
                                text: el.textContent?.trim(),
                                className: el.className
                            })).filter(x => x.text && x.text.length > 0);
                        }
                    """)

                    if text_content:
                        # Process extracted data
                        for item in text_content:
                            text = item.get("text", "")
                            if text and len(text) > 5:
                                evidence_items.append(
                                    {
                                        "titulo": f"Power BI PBIA - {text[:50]}",
                                        "descricao": text,
                                        "data": now,
                                        "fonte_url": self.dashboard_url,
                                        "tipo": "relatorio",
                                        "confianca": 0.5,
                                        "metadata": {
                                            "source": "powerbi_cgee",
                                            "element_type": item.get("tag"),
                                            "class": item.get("className", "")[:100],
                                            # Texto arbitrário do DOM do dashboard;
                                            # não é uma métrica validada.
                                            "metodo": "dom_text_arbitrario",
                                            "provisional": True,
                                        },
                                    }
                                )

                except Exception as e:
                    logger.debug(f"Error processing frame: {e}")
                    continue

            # Take screenshot for reference — preservada como artefato
            # (byte payload em base64 + metadados), não apenas o tamanho.
            try:
                screenshot = await page.screenshot(full_page=True)
                logger.info(f"Screenshot captured: {len(screenshot)} bytes")
                # Store screenshot as evidence
                evidence_items.append(
                    {
                        "titulo": "Screenshot do Dashboard PBIA - CGEE",
                        "descricao": f"Captura de tela do dashboard Power BI em {now}",
                        "data": now,
                        "fonte_url": self.dashboard_url,
                        "tipo": "relatorio",
                        "confianca": 0.6,
                        "metadata": {
                            "source": "powerbi_cgee",
                            "screenshot_size": len(screenshot),
                            "format": "png",
                        },
                        "artefato": {
                            "nome": "pbia_powerbi_dashboard.png",
                            "mime": "image/png",
                            "formato": "png",
                            "tamanho_bytes": len(screenshot),
                            "conteudo_base64": base64.b64encode(screenshot).decode("ascii"),
                        },
                    }
                )
            except Exception as e:
                logger.warning(f"Failed to capture screenshot: {e}")

            self.provenance.add_record(
                url=self.dashboard_url,
                method="playwright_scraping",
                confidence=0.7,
                metadata={
                    "source": "pbia_powerbi",
                    "evidence_count": len(evidence_items),
                    "frames_found": len(frames),
                },
            )

            logger.info(f"Power BI scraping completed: {len(evidence_items)} items extracted")

        except Exception as e:
            logger.error(f"Power BI scraping failed: {e}")
            evidence_items.append(
                {
                    "titulo": "Erro ao acessar Dashboard PBIA - CGEE",
                    "descricao": f"Falha ao acessar {self.dashboard_url}: {e!s}",
                    "data": now,
                    "fonte_url": self.dashboard_url,
                    "tipo": "outro",
                    "confianca": 0.3,
                    "metadata": {
                        "source": "powerbi_cgee",
                        "error": str(e),
                    },
                }
            )
        finally:
            # Garante que Playwright/browser sejam fechados mesmo em caso de erro.
            await self.close()

        return evidence_items

    async def get_provenance_records(self) -> list[dict[str, Any]]:
        """Retorna os registros de proveniência."""
        records = self.provenance.get_records()
        return [record.model_dump() for record in records]

    async def close(self) -> None:
        """Limpa recursos do browser."""
        try:
            if self._browser:
                await self._browser.close()
            if self._playwright:
                await self._playwright.stop()
        except Exception as e:
            logger.warning(f"Error closing Playwright: {e}")
