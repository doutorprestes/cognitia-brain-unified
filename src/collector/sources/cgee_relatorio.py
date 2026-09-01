"""IA Brasil — Coletor do Relatório CGEE de execução do PBIA.

Parceria de dados CGEE/OBIA (issue #1103): o **Relatório CGEE "Resultados da
implementação e monitoramento do PBIA 2024-2025"** (~08/04/2026) é a fonte
primária dos números oficiais de execução do PBIA. O monitor oficial é o
portal CGEE (`pbia.cgee.org.br`) e o OBIA (NIC.br/CGI.br, Eixo 5).

Este coletor busca a **página** do portal CGEE do PBIA (a URL direta do PDF
não é estável/accessível) e tenta extrair:

- título do relatório mais recente;
- data de referência (`ultima_referencia`);
- URL do PDF (quando um link ``*.pdf`` é encontrado na página);
- números-chave de execução (ex.: % de ações com avanço, valores em R$)
  **quando parseáveis**.

Quando o conteúdo não é parseável, retorna **uma** evidência com abstenção
honesta: metadata com ``dados_estaticos``/``provisional`` e ``aviso``
explicando o que não pôde ser extraído (padrão do OBIA, issue #1088) — sem
inventar números.

Cadência declarada (modelo NextGenEU): ``PERIODICIDADE = "2x/ano"``. O
scheduler lê ``PERIODICIDADE`` (classe) e ``ultima_referencia`` (instância)
para registrar a cadência no ``IngestionRun.metadata_json``.

Uso:
    from src.collector.sources.cgee_relatorio import CgeeRelatorioCollector

    collector = CgeeRelatorioCollector()
    items = await collector.collect()
"""

from __future__ import annotations

import re
from datetime import UTC, date, datetime
from typing import Any

from loguru import logger

from src.collector.core.fetcher import HTTPFetcher
from src.collector.core.provenance import ProvenanceTracker

# URLs candidatas da página do PBIA no portal CGEE (a primeira que responder
# 200 com conteúdo vence). A URL do PDF em si não é estável — coletamos a
# página e tentamos extrair o link do PDF.
CGEE_PAGES = [
    "https://www.cgee.org.br/web/pbia",
    "https://pbia.cgee.org.br",
    "https://www.cgee.org.br/publicacoes",
]

# Título conhecido do relatório oficial (fonte primária dos números).
RELATORIO_TITULO_CONHECIDO = "Resultados da implementação e monitoramento do PBIA 2024-2025"

_AVISO_ABSTENCAO = (
    "Abstenção honesta: a página do portal CGEE não permitiu extrair os "
    "números-chave de execução de forma confiável. Apenas o título/URL da "
    "página são registrados como dados estáticos/provisórios — nenhum número "
    "foi inventado. Verificar o PDF do relatório diretamente."
)

# Data dd/mm/aaaa ou ISO aaaa-mm-dd.
_DATE_RE = re.compile(r"(?:\b(\d{1,2})/(\d{1,2})/(\d{4})\b|\b(\d{4})-(\d{2})-(\d{2})\b)")
# Link de PDF (href).
_PDF_HREF_RE = re.compile(r'<a[^>]+href=["\']([^"\']+\.pdf(?:[?#][^"\']*)?)["\']', re.IGNORECASE)
# % de ações/metas com avanço ou em execução.
_PCT_AVANCO_RE = re.compile(
    r"(\d{1,3}(?:[.,]\d+)?)\s*%\s*(?:d[ae]s?\s+)?"
    r"(?:a[çc][õo]es|metas|itens)?\s*"
    r"(?:com\s+algum\s+avan[çc]o|avan[çc]ad[oa]s?|em\s+execu[çc][ãa]o)",
    re.IGNORECASE,
)
# Valores em R$ (bi / milhões).
_VALOR_RE = re.compile(r"R\$\s*([\d.,]+)\s*(bilh[oõ]es?|bi|milh[oõ]es?|mi)?", re.IGNORECASE)


class CgeeRelatorioCollector:
    """Coleta a página do portal CGEE do PBIA e extrai o relatório oficial.

    Attributes:
        base_url: Primeira URL candidata do portal CGEE.
        fetcher: Instância do HTTPFetcher.
        provenance: Instância do ProvenanceTracker.
        ultima_referencia: Data do relatório mais recente (extraída na coleta)
            ou None quando não parseável. Consumida pelo scheduler para a
            cadência declarada do run (issue #1103).
    """

    # Versão do parser/coletor (registrada no IngestionRun — issue #1087).
    PARSER_VERSION = "1.0.0"

    # Cadência declarada de reporte do monitor oficial (modelo NextGenEU: 2x/ano).
    PERIODICIDADE = "2x/ano"

    def __init__(self) -> None:
        self.base_url = CGEE_PAGES[0]
        self.fetcher = HTTPFetcher(rate_limit=2, cache_ttl=600)
        self.provenance = ProvenanceTracker()
        self.ultima_referencia: date | None = None

    # ------------------------------------------------------------------
    # Parsing (puro, testável sem rede)
    # ------------------------------------------------------------------

    @staticmethod
    def _extract_title(html: str) -> str:
        """Extrai o título do relatório a partir do HTML da página."""
        match = re.search(r"<title[^>]*>(.*?)</title>", html, re.IGNORECASE | re.DOTALL)
        if match:
            title = match.group(1).strip()
            if title:
                return title[:300]
        match = re.search(
            r'<meta[^>]+property=["\']og:title["\'][^>]+content=["\']([^"\']+)',
            html,
            re.IGNORECASE,
        )
        if match:
            return match.group(1).strip()[:300]
        match = re.search(r"<h1[^>]*>(.*?)</h1>", html, re.IGNORECASE | re.DOTALL)
        if match:
            return re.sub(r"<[^>]+>", "", match.group(1)).strip()[:300]
        return ""

    @staticmethod
    def _extract_pdf_url(html: str) -> str | None:
        """Extrai a primeira URL de PDF da página (preferindo links do CGEE)."""
        matches: list[str] = _PDF_HREF_RE.findall(html)
        if not matches:
            return None
        for url in matches:
            if "cgee.org.br" in url:
                return url
        return matches[0]

    @staticmethod
    def _extract_data_referencia(html: str) -> datetime | None:
        """Extrai a data mais recente presente na página (dd/mm/aaaa ou ISO).

        A página do portal pode listar várias datas (navegação, destaques).
        Como o relatório oficial é o documento mais recente da série, adotamos
        a data mais recente encontrada. Retorna None quando nenhuma data
        confiável é encontrada (abstenção).
        """
        dates: list[datetime] = []
        for m in _DATE_RE.finditer(html):
            if m.group(1):  # dd/mm/aaaa
                day, month, year = int(m.group(1)), int(m.group(2)), int(m.group(3))
            else:  # aaaa-mm-dd
                year, month, day = int(m.group(4)), int(m.group(5)), int(m.group(6))
            if not (1 <= month <= 12 and 1 <= day <= 31):
                continue
            try:
                dates.append(datetime(year, month, day))
            except ValueError:
                continue
        if not dates:
            return None
        dates.sort()
        return dates[-1]

    @staticmethod
    def _extract_numeros_chave(html: str) -> list[dict[str, Any]]:
        """Tenta extrair números-chave de execução (heurístico, provisório).

        Returns:
            Lista de dicts com ``tipo``, ``valor``, ``unidade`` e
            ``texto_completo``. Vazia quando nada é encontrado — o chamador
            deve abster-se (não inventar números).
        """
        numeros: list[dict[str, Any]] = []
        for match in _PCT_AVANCO_RE.finditer(html):
            valor_raw = match.group(1).replace(".", "").replace(",", ".")
            try:
                valor = float(valor_raw)
            except ValueError:
                continue
            numeros.append(
                {
                    "tipo": "percentual_avancos",
                    "valor": valor,
                    "unidade": "%",
                    "texto_completo": match.group(0).strip()[:200],
                }
            )
        for match in _VALOR_RE.finditer(html):
            valor_raw = match.group(1).replace(".", "").replace(",", ".")
            try:
                valor = float(valor_raw)
            except ValueError:
                continue
            unidade = "R$"
            if match.group(2):
                unidade = f"R$ {match.group(2)}"
            numeros.append(
                {
                    "tipo": "valor_execucao",
                    "valor": valor,
                    "unidade": unidade,
                    "texto_completo": match.group(0).strip()[:200],
                }
            )
        return numeros[:10]

    def parse_page(self, html: str, url: str) -> dict[str, Any]:
        """Analisa o HTML da página e monta o dict de informações do relatório.

        Args:
            html: Conteúdo HTML da página.
            url: URL da página coletada.

        Returns:
            Dict com titulo, ultima_referencia, url_pdf, numeros_chave e
            status_parse ("ok" quando números/data foram extraídos, caso
            contrário "abstencao").
        """
        titulo = self._extract_title(html)
        if not titulo:
            titulo = RELATORIO_TITULO_CONHECIDO
        ultima_referencia = self._extract_data_referencia(html)
        url_pdf = self._extract_pdf_url(html)
        numeros = self._extract_numeros_chave(html)

        status_parse = "ok" if numeros or ultima_referencia is not None else "abstencao"

        return {
            "url": url,
            "titulo": titulo,
            "ultima_referencia": ultima_referencia,
            "url_pdf": url_pdf,
            "numeros_chave": numeros,
            "status_parse": status_parse,
        }

    # ------------------------------------------------------------------
    # Coleta
    # ------------------------------------------------------------------

    async def _fetch_first_page(self) -> tuple[str, str] | None:
        """Busca a primeira página candidata que responde 200 com conteúdo."""
        async with self.fetcher as fetcher:
            for url in CGEE_PAGES:
                try:
                    response = await fetcher.fetch(url, use_cache=False)
                except Exception as e:
                    logger.warning(f"[CGEE] Falha ao buscar {url}: {e}")
                    continue
                if response.status != 200:
                    logger.warning(f"[CGEE] {url} retornou status {response.status}")
                    continue
                html = response.data if isinstance(response.data, str) else str(response.data)
                if html.strip():
                    return url, html
        return None

    def _build_item(
        self,
        *,
        titulo: str,
        descricao: str,
        fonte_url: str,
        info: dict[str, Any] | None,
        confianca: float,
        aviso: str | None,
    ) -> dict[str, Any]:
        """Monta o item de evidência padronizado com metadata honesta."""
        metadata: dict[str, Any] = {
            "fonte": "CGEE",
            "tipo": "relatorio_execucao",
            "periodicidade": self.PERIODICIDADE,
            "status_parse": (info or {}).get("status_parse", "abstencao"),
        }
        if info is not None:
            ultima_ref = info.get("ultima_referencia")
            if isinstance(ultima_ref, date):
                self.ultima_referencia = ultima_ref
                metadata["ultima_referencia"] = ultima_ref.isoformat()
            if info.get("titulo"):
                metadata["titulo_relatorio"] = info["titulo"]
            if info.get("url_pdf"):
                metadata["url_pdf"] = info["url_pdf"]
            numeros = info.get("numeros_chave") or []
            if numeros:
                metadata["numeros_chave"] = numeros
                metadata["dados_estaticos"] = False
                metadata["provisional"] = True  # extração heurística de HTML
            else:
                metadata["dados_estaticos"] = True
                metadata["provisional"] = True
        else:
            metadata["dados_estaticos"] = True
            metadata["provisional"] = True

        if aviso:
            metadata["aviso"] = aviso

        return {
            "titulo": titulo,
            "descricao": descricao,
            "data": datetime.now(UTC).isoformat(),
            "fonte_url": fonte_url,
            "tipo": "relatorio",
            "confianca": confianca,
            "metadata": metadata,
        }

    async def collect(self) -> list[dict[str, Any]]:
        """Coleta a página do portal CGEE e extrai o relatório oficial.

        Returns:
            Lista com uma evidência do relatório (parseada ou abstenção
            honesta). Nunca retorna lista vazia: falha de acesso também gera
            um item com abstenção, evitando quarentena injustificada.
        """
        page = await self._fetch_first_page()

        if page is None:
            logger.error("[CGEE] Nenhuma página do portal CGEE acessível")
            self.provenance.add_record(
                url=self.base_url,
                method="GET",
                confidence=0.2,
                metadata={"source": "cgee_relatorio", "success": False},
            )
            return [
                self._build_item(
                    titulo="CGEE — Relatório de execução do PBIA (não acessível)",
                    descricao=(
                        "Falha ao acessar a página do portal CGEE do PBIA. "
                        "Nenhum dado foi extraído — nenhum número foi inventado."
                    ),
                    fonte_url=self.base_url,
                    info=None,
                    confianca=0.2,
                    aviso="falha de acesso à página do portal CGEE",
                )
            ]

        url, html = page
        info = self.parse_page(html, url)
        logger.info(
            f"[CGEE] Página {url} — status_parse={info['status_parse']}, "
            f"numeros={len(info['numeros_chave'])}, "
            f"pdf={bool(info['url_pdf'])}"
        )

        self.provenance.add_record(
            url=url,
            method="GET",
            confidence=0.8 if info["status_parse"] == "ok" else 0.5,
            metadata={
                "source": "cgee_relatorio",
                "status_parse": info["status_parse"],
                "dados_estaticos": True,
                "success": True,
            },
        )

        titulo = info["titulo"] or RELATORIO_TITULO_CONHECIDO
        descricao = (
            f"Relatório oficial de execução do PBIA publicado pela CGEE "
            f"('{titulo}'). Fonte declarada: {url}."
        )
        if info["url_pdf"]:
            descricao += f" PDF: {info['url_pdf']}."
        if info["numeros_chave"]:
            descricao += (
                f" Números-chave extraídos da página (provisórios): "
                f"{'; '.join(n['texto_completo'] for n in info['numeros_chave'][:3])}."
            )
        else:
            descricao += " Números de execução não extraíveis da página (abstenção)."

        aviso = None if info["status_parse"] == "ok" else _AVISO_ABSTENCAO

        return [
            self._build_item(
                titulo=f"CGEE — {titulo}",
                descricao=descricao,
                fonte_url=url,
                info=info,
                confianca=0.8,
                aviso=aviso,
            )
        ]

    async def get_provenance_records(self) -> list[dict[str, Any]]:
        """Retorna os registros de proveniência da coleta.

        Returns:
            Lista de registros de proveniência (dicts).
        """
        records = self.provenance.get_records()
        return [record.model_dump() for record in records]

    async def close(self) -> None:
        """Limpa recursos do fetcher."""
        await self.fetcher.close()
