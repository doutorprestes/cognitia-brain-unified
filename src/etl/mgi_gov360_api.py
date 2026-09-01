import argparse
import csv
import json
import logging
from collections import Counter
from datetime import datetime, timezone
from io import StringIO
from pathlib import Path
from typing import Any

import requests


logging.basicConfig(level=logging.INFO, format="%(levelname)s:%(name)s:%(message)s")
logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DATA_DIR = PROJECT_ROOT / "etl" / "data"


class MGIGov360Client:
    SOURCE_ID = "mgi_gov360_raiox"
    SOURCE_NAME = "MGI/SEGES - Gov360 Raio-X da Administração Pública Federal"
    OFFICIAL_URL = "https://repositorio.dados.gov.br/seges/raio-x/"
    DATAPACKAGE_URL = OFFICIAL_URL + "datapackage.json"
    TRANSFORMACAO_DIGITAL_URL = OFFICIAL_URL + "transformacao-digital.csv"
    SOLUCOES_MODERNIZACAO_URL = OFFICIAL_URL + "solucoes-modernizacao.csv"

    def __init__(self, data_dir: Path = DEFAULT_DATA_DIR, timeout: int = 45):
        self.data_dir = Path(data_dir)
        self.timeout = timeout
        self.raw_dir = self.data_dir / "raw"
        self.processed_dir = self.data_dir / "processed"
        self.catalog_dir = self.data_dir / "catalog"

    def ensure_dirs(self) -> None:
        for directory in [self.raw_dir, self.processed_dir, self.catalog_dir]:
            directory.mkdir(parents=True, exist_ok=True)

    def fetch_text(self, url: str) -> str:
        response = requests.get(url, timeout=self.timeout, headers={"User-Agent": "InvestIA/0.1"})
        response.raise_for_status()
        response.encoding = response.apparent_encoding or response.encoding or "utf-8"
        return response.text

    def fetch_json(self, url: str) -> dict[str, Any]:
        response = requests.get(url, timeout=self.timeout, headers={"User-Agent": "InvestIA/0.1"})
        response.raise_for_status()
        return response.json()

    @staticmethod
    def parse_csv(text: str) -> list[dict[str, str]]:
        return list(csv.DictReader(StringIO(text)))

    @staticmethod
    def digital_summary(rows: list[dict[str, str]]) -> dict[str, Any]:
        latest_ref = max((row.get("ano_mes_referencia") or "" for row in rows), default="")
        latest_rows = [row for row in rows if row.get("ano_mes_referencia") == latest_ref] if latest_ref else rows
        status_counts = Counter(row.get("situacao_raiox") or row.get("situacao") or "não informado" for row in latest_rows)
        superior_counts = Counter(row.get("orgao_superior_sigla") or row.get("orgao_superior_nome") or "não informado" for row in latest_rows)
        area_counts = Counter(row.get("area") or "não informado" for row in latest_rows)
        digital_rows = [
            row
            for row in latest_rows
            if (row.get("situacao_raiox") or row.get("situacao") or "").lower() in {"digital", "digitalizado"}
        ]
        return {
            "latest_reference": latest_ref,
            "services_count": len(latest_rows),
            "digital_services_count": len(digital_rows),
            "digital_services_percent": round((len(digital_rows) / len(latest_rows) * 100), 2) if latest_rows else None,
            "status_counts": dict(status_counts.most_common()),
            "top_superior_organs": dict(superior_counts.most_common(10)),
            "top_service_areas": dict(area_counts.most_common(10)),
        }

    @staticmethod
    def modernization_summary(rows: list[dict[str, str]]) -> dict[str, Any]:
        fieldnames = rows[0].keys() if rows else []
        text_fields = [field for field in fieldnames if field]
        matched_rows = [
            row
            for row in rows
            if any(
                term in " ".join(str(row.get(field, "")).lower() for field in text_fields)
                for term in ["inteligência artificial", "inteligencia artificial", "analytics", "dados", "automação", "automacao"]
            )
        ]
        return {
            "solutions_count": len(rows),
            "ai_or_data_related_count": len(matched_rows),
            "sample": matched_rows[:10],
        }

    def run(self) -> dict[str, Any]:
        self.ensure_dirs()
        collected_at = datetime.now(timezone.utc).isoformat()
        raw_datapackage_path = self.raw_dir / "mgi_gov360_datapackage.json"
        raw_transformacao_path = self.raw_dir / "mgi_gov360_transformacao_digital.csv"
        raw_solucoes_path = self.raw_dir / "mgi_gov360_solucoes_modernizacao.csv"
        processed_path = self.processed_dir / "mgi_gov360_raiox.json"
        catalog_path = self.catalog_dir / "mgi_gov360_raiox_status.json"

        datapackage = self.fetch_json(self.DATAPACKAGE_URL)
        transformacao_text = self.fetch_text(self.TRANSFORMACAO_DIGITAL_URL)
        solucoes_text = self.fetch_text(self.SOLUCOES_MODERNIZACAO_URL)
        transformacao_rows = self.parse_csv(transformacao_text)
        solucoes_rows = self.parse_csv(solucoes_text)

        raw_datapackage_path.write_text(json.dumps(datapackage, ensure_ascii=False, indent=2), encoding="utf-8")
        raw_transformacao_path.write_text(transformacao_text, encoding="utf-8")
        raw_solucoes_path.write_text(solucoes_text, encoding="utf-8")

        processed = {
            "source_id": self.SOURCE_ID,
            "source_name": self.SOURCE_NAME,
            "official_url": self.OFFICIAL_URL,
            "collection_method": "Arquivos CSV e Data Package oficiais em repositorio.dados.gov.br",
            "collected_at": collected_at,
            "schema_version": "1.0",
            "is_demo": False,
            "data_scope": "institutional_capacity",
            "dataset_title": datapackage.get("title"),
            "dataset_name": datapackage.get("name"),
            "digital_transformation": self.digital_summary(transformacao_rows),
            "modernization_solutions": self.modernization_summary(solucoes_rows),
            "known_limitations": (
                "Gov360/Raio-X mede capacidade institucional e transformação digital do Executivo Federal; "
                "não é uma métrica específica de adoção de IA e deve ser cruzado com MGI/OBIA, DOU e compras públicas."
            ),
        }
        processed_path.write_text(json.dumps(processed, ensure_ascii=False, indent=2), encoding="utf-8")

        catalog = {
            "source_id": self.SOURCE_ID,
            "source_name": self.SOURCE_NAME,
            "official_url": self.OFFICIAL_URL,
            "collection_method": processed["collection_method"],
            "update_frequency": "Mensal",
            "raw_format": "json/csv",
            "processed_format": "json",
            "schema_version": "1.0",
            "collected_at": collected_at,
            "period_start": processed["digital_transformation"].get("latest_reference"),
            "period_end": processed["digital_transformation"].get("latest_reference"),
            "processed_count": processed["digital_transformation"].get("services_count"),
            "raw_file": raw_datapackage_path.relative_to(self.data_dir).as_posix(),
            "processed_file": processed_path.relative_to(self.data_dir).as_posix(),
            "is_demo": False,
            "known_limitations": processed["known_limitations"],
        }
        catalog_path.write_text(json.dumps(catalog, ensure_ascii=False, indent=2), encoding="utf-8")
        logger.info("Saved MGI Gov360 processed data to %s", processed_path)
        return catalog


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Coleta Gov360/Raio-X da Administração Pública Federal.")
    parser.add_argument("--data-dir", default=str(DEFAULT_DATA_DIR), help="Diretório de saída dos dados.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    result = MGIGov360Client(data_dir=Path(args.data_dir)).run()
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
