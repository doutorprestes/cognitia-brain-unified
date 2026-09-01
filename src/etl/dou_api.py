import argparse
import csv
import json
import logging
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

import requests


logging.basicConfig(level=logging.INFO, format="%(levelname)s:%(name)s:%(message)s")
logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DATA_DIR = PROJECT_ROOT / "etl" / "data"

DOU_TERMS = [
    "inteligência artificial",
    "ciência tecnologia inovação",
    "transformação digital",
    "fomento pesquisa inovação",
    "governança de dados",
]


class DOUAPIClient:
    SOURCE_ID = "dou_publicacoes"
    SOURCE_NAME = "Diário Oficial da União"
    OFFICIAL_URL = "https://www.in.gov.br/web/dou"
    SEARCH_URL = "https://www.in.gov.br/consulta/-/buscar/dou"

    def __init__(self, data_dir: Path = DEFAULT_DATA_DIR, timeout: int = 30):
        self.data_dir = Path(data_dir)
        self.timeout = timeout
        self.raw_dir = self.data_dir / "raw"
        self.processed_dir = self.data_dir / "processed"
        self.catalog_dir = self.data_dir / "catalog"

    def ensure_dirs(self) -> None:
        for directory in [self.raw_dir, self.processed_dir, self.catalog_dir]:
            directory.mkdir(parents=True, exist_ok=True)

    def fetch_term(self, term: str, exact_date: str) -> dict[str, Any]:
        response = requests.get(
            self.SEARCH_URL,
            params={"q": term, "exactDate": exact_date, "sortType": "0"},
            timeout=self.timeout,
            headers={"User-Agent": "InvestIA/0.1"},
        )
        response.raise_for_status()
        return {
            "term": term,
            "exact_date": exact_date,
            "url": response.url,
            "content_type": response.headers.get("content-type"),
            "html": response.text,
        }

    def normalize_exact_date(self, exact_date: str | None) -> tuple[str, str]:
        if not exact_date:
            today = date.today()
            return today.strftime("%d-%m-%Y"), today.isoformat()
        for date_format in ("%d-%m-%Y", "%Y-%m-%d"):
            try:
                parsed = datetime.strptime(exact_date, date_format).date()
                return parsed.strftime("%d-%m-%Y"), parsed.isoformat()
            except ValueError:
                continue
        raise ValueError("Data DOU deve estar em DD-MM-YYYY ou YYYY-MM-DD.")

    def process_payloads(self, payloads: list[dict[str, Any]], collected_at: str, iso_date: str) -> list[dict[str, Any]]:
        rows = []
        for payload in payloads:
            html = payload["html"]
            if payload["term"].lower() not in html.lower():
                continue
            rows.append(
                {
                    "date": iso_date,
                    "title": f"Resultado oficial para {payload['term']}",
                    "section": "",
                    "type": "Busca DOU",
                    "source": self.SOURCE_NAME,
                    "description": "Resultado bruto da busca oficial do DOU preservado no diretório raw.",
                    "url": payload["url"],
                    "term": payload["term"],
                    "source_id": self.SOURCE_ID,
                    "source_name": self.SOURCE_NAME,
                    "official_url": self.OFFICIAL_URL,
                    "collected_at": collected_at,
                    "is_demo": "false",
                }
            )
        return rows

    def run(self, exact_date: str | None = None, terms: list[str] | None = None) -> dict[str, Any]:
        self.ensure_dirs()
        collected_at = datetime.now(timezone.utc).isoformat()
        exact_date, iso_date = self.normalize_exact_date(exact_date)
        selected_terms = terms or DOU_TERMS
        raw_path = self.raw_dir / "dou_publicacoes.json"
        processed_path = self.processed_dir / "dou_publicacoes.csv"
        catalog_path = self.catalog_dir / "dou_publicacoes_status.json"

        try:
            payloads = [self.fetch_term(term, exact_date) for term in selected_terms]
            rows = self.process_payloads(payloads, collected_at, iso_date)
            raw_path.write_text(json.dumps(payloads, ensure_ascii=False, indent=2), encoding="utf-8")
            with processed_path.open("w", encoding="utf-8", newline="") as csv_file:
                fieldnames = ["date", "title", "section", "type", "source", "description", "url", "term", "source_id", "source_name", "official_url", "collected_at", "is_demo"]
                writer = csv.DictWriter(csv_file, fieldnames=fieldnames)
                writer.writeheader()
                writer.writerows(rows)
            catalog = {
                "source_id": self.SOURCE_ID,
                "source_name": self.SOURCE_NAME,
                "official_url": self.OFFICIAL_URL,
                "collection_method": "Busca oficial do portal DOU",
                "update_frequency": "Dias úteis",
                "raw_format": "json",
                "processed_format": "csv",
                "schema_version": "1.0",
                "collected_at": collected_at,
                "period_start": iso_date,
                "period_end": iso_date,
                "processed_count": len(rows),
                "raw_file": raw_path.relative_to(self.data_dir).as_posix(),
                "processed_file": processed_path.relative_to(self.data_dir).as_posix(),
                "is_demo": False,
                "known_limitations": "Coleta inicial usa busca oficial e preserva HTML bruto; extração semântica de atos ainda precisa ser endurecida.",
            }
        except (requests.RequestException, ValueError) as error:
            catalog = {
                "source_id": self.SOURCE_ID,
                "source_name": self.SOURCE_NAME,
                "official_url": self.OFFICIAL_URL,
                "collection_method": "Busca oficial do portal DOU",
                "update_frequency": "Dias úteis",
                "schema_version": "1.0",
                "collected_at": collected_at,
                "period_start": exact_date,
                "period_end": exact_date,
                "status": "failed",
                "last_error": str(error),
                "is_demo": True,
                "known_limitations": "A busca oficial do DOU falhou; nenhum item demonstrativo foi gravado como real.",
            }

        catalog_path.write_text(json.dumps(catalog, ensure_ascii=False, indent=2), encoding="utf-8")
        logger.info("Saved DOU catalog status to %s", catalog_path)
        return catalog


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Coleta publicações do DOU pela busca oficial.")
    parser.add_argument("--date", default=None, help="Data exata no formato DD-MM-YYYY.")
    parser.add_argument("--data-dir", default=str(DEFAULT_DATA_DIR), help="Diretório de saída dos dados.")
    parser.add_argument("--term", action="append", dest="terms", help="Termo de busca; pode ser repetido.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    result = DOUAPIClient(data_dir=Path(args.data_dir)).run(exact_date=args.date, terms=args.terms)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
