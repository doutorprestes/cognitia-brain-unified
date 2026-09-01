import argparse
import csv
import json
import logging
import re
from datetime import datetime, timezone
from html import unescape
from pathlib import Path
from typing import Any

import requests


logging.basicConfig(level=logging.INFO, format="%(levelname)s:%(name)s:%(message)s")
logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DATA_DIR = PROJECT_ROOT / "etl" / "data"


class FINEPAPIClient:
    SOURCE_ID = "finep_chamadas"
    SOURCE_NAME = "FINEP - Chamadas Públicas"
    OFFICIAL_URL = "https://www.finep.gov.br/chamadas-publicas"

    def __init__(self, data_dir: Path = DEFAULT_DATA_DIR, timeout: int = 30):
        self.data_dir = Path(data_dir)
        self.timeout = timeout
        self.raw_dir = self.data_dir / "raw"
        self.processed_dir = self.data_dir / "processed"
        self.catalog_dir = self.data_dir / "catalog"

    def ensure_dirs(self) -> None:
        for directory in [self.raw_dir, self.processed_dir, self.catalog_dir]:
            directory.mkdir(parents=True, exist_ok=True)

    def fetch_page(self) -> str:
        response = requests.get(self.OFFICIAL_URL, timeout=self.timeout, headers={"User-Agent": "InvestIA/0.1"})
        response.raise_for_status()
        response.encoding = response.apparent_encoding or response.encoding or "utf-8"
        return response.text

    def parse_calls(self, html: str, collected_at: str) -> list[dict[str, Any]]:
        matches = re.findall(r'<a[^>]+href="([^"]*chamadas-publicas[^"]*)"[^>]*>(.*?)</a>', html, flags=re.I | re.S)
        rows: list[dict[str, Any]] = []
        seen: set[str] = set()
        for href, title_html in matches:
            if "/chamadapublica/" not in href:
                continue
            title = re.sub(r"<[^>]+>", " ", title_html)
            title = re.sub(r"\s+", " ", unescape(title)).strip()
            if not title or title in seen:
                continue
            seen.add(title)
            url = href if href.startswith("http") else f"https://www.finep.gov.br{href}"
            rows.append(
                {
                    "title": title,
                    "url": url,
                    "status": "identificada_na_pagina_oficial",
                    "instrument": infer_instrument(title),
                    "theme_hint": infer_theme_hint(title),
                    "target_audience": "",
                    "opens_at": "",
                    "closes_at": "",
                    "amount": "",
                    "source_id": self.SOURCE_ID,
                    "source_name": self.SOURCE_NAME,
                    "official_url": self.OFFICIAL_URL,
                    "collected_at": collected_at,
                    "is_demo": False,
                    "known_limitations": "Parser inicial sobre página oficial; revisar manualmente se a estrutura HTML da FINEP mudar.",
                }
            )
        return rows

    def run(self) -> dict[str, Any]:
        self.ensure_dirs()
        collected_at = datetime.now(timezone.utc).isoformat()
        raw_path = self.raw_dir / "finep_chamadas.html"
        processed_path = self.processed_dir / "finep_chamadas.csv"
        catalog_path = self.catalog_dir / "finep_chamadas_status.json"

        try:
            html = self.fetch_page()
            rows = self.parse_calls(html, collected_at)
            raw_path.write_text(html, encoding="utf-8")
            with processed_path.open("w", encoding="utf-8", newline="") as csv_file:
                fieldnames = [
                    "title",
                    "url",
                    "status",
                    "instrument",
                    "theme_hint",
                    "target_audience",
                    "opens_at",
                    "closes_at",
                    "amount",
                    "source_id",
                    "source_name",
                    "official_url",
                    "collected_at",
                    "is_demo",
                    "known_limitations",
                ]
                writer = csv.DictWriter(csv_file, fieldnames=fieldnames)
                writer.writeheader()
                writer.writerows(rows)
            catalog = {
                "source_id": self.SOURCE_ID,
                "source_name": self.SOURCE_NAME,
                "official_url": self.OFFICIAL_URL,
                "collection_method": "Página oficial FINEP",
                "update_frequency": "Semanal",
                "raw_format": "html",
                "processed_format": "csv",
                "schema_version": "1.0",
                "collected_at": collected_at,
                "processed_count": len(rows),
                "raw_file": raw_path.relative_to(self.data_dir).as_posix(),
                "processed_file": processed_path.relative_to(self.data_dir).as_posix(),
                "is_demo": False,
                "known_limitations": "Parser inicial sobre página oficial; evitar inferência financeira sem validação manual.",
            }
        except requests.RequestException as error:
            catalog = {
                "source_id": self.SOURCE_ID,
                "source_name": self.SOURCE_NAME,
                "official_url": self.OFFICIAL_URL,
                "collection_method": "Página oficial FINEP",
                "update_frequency": "Semanal",
                "schema_version": "1.0",
                "collected_at": collected_at,
                "status": "failed",
                "last_error": str(error),
                "is_demo": True,
                "known_limitations": "A página oficial não pôde ser coletada; nenhum valor demonstrativo foi gravado como real.",
            }

        catalog_path.write_text(json.dumps(catalog, ensure_ascii=False, indent=2), encoding="utf-8")
        logger.info("Saved FINEP catalog status to %s", catalog_path)
        return catalog


def infer_instrument(title: str) -> str:
    normalized = title.lower()
    if "subven" in normalized:
        return "subvencao_economica"
    if "proinfra" in normalized:
        return "infraestrutura_pesquisa"
    if "mais inovação" in normalized or "mais inovacao" in normalized:
        return "credito_inovacao"
    return "chamada_publica"


def infer_theme_hint(title: str) -> str:
    normalized = title.lower()
    if "defesa" in normalized:
        return "base_industrial_defesa"
    if "agro" in normalized or "agricultura" in normalized:
        return "agroindustria"
    if "infra" in normalized:
        return "infraestrutura_cti"
    if "digital" in normalized or "ia" in normalized or "intelig" in normalized:
        return "inteligencia_artificial_transformacao_digital"
    return "inovacao_tecnologica"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Coleta chamadas públicas da FINEP a partir da página oficial.")
    parser.add_argument("--data-dir", default=str(DEFAULT_DATA_DIR), help="Diretório de saída dos dados.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    result = FINEPAPIClient(data_dir=Path(args.data_dir)).run()
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
