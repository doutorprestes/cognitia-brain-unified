import argparse
import csv
import json
import logging
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import requests


logging.basicConfig(level=logging.INFO, format="%(levelname)s:%(name)s:%(message)s")
logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DATA_DIR = PROJECT_ROOT / "etl" / "data"

AI_TERMS = [
    "inteligência artificial",
    "inteligencia artificial",
    " ia ",
    "ia generativa",
    "aprendizado de máquina",
    "machine learning",
    "chatbot",
    "visão computacional",
    "processamento de linguagem natural",
    "analytics",
    "ciência de dados",
    "ciencia de dados",
    "automação",
    "automacao",
]


class ComprasGovClient:
    SOURCE_ID = "compras_gov_abertas"
    SOURCE_NAME = "Compras.gov.br - Dados Abertos"
    OFFICIAL_URL = "https://dadosabertos.compras.gov.br/swagger-ui/index.html"
    OPENAPI_URL = "https://dadosabertos.compras.gov.br/v3/api-docs"
    LEGACY_LICITACOES_URL = "https://dadosabertos.compras.gov.br/modulo-legado/1_consultarLicitacao"

    def __init__(self, data_dir: Path = DEFAULT_DATA_DIR, timeout: int = 20):
        self.data_dir = Path(data_dir)
        self.timeout = timeout
        self.raw_dir = self.data_dir / "raw"
        self.processed_dir = self.data_dir / "processed"
        self.catalog_dir = self.data_dir / "catalog"

    def ensure_dirs(self) -> None:
        for directory in [self.raw_dir, self.processed_dir, self.catalog_dir]:
            directory.mkdir(parents=True, exist_ok=True)

    def fetch_openapi(self) -> dict[str, Any]:
        response = requests.get(self.OPENAPI_URL, timeout=self.timeout, headers={"User-Agent": "InvestIA/0.1"})
        response.raise_for_status()
        return response.json()

    def fetch_legacy_licitacoes(self, start_date: str, end_date: str, page_size: int = 10) -> Any:
        response = requests.get(
            self.LEGACY_LICITACOES_URL,
            params={
                "data_publicacao_inicial": start_date,
                "data_publicacao_final": end_date,
                "pagina": 1,
                "tamanhoPagina": page_size,
            },
            timeout=self.timeout,
            headers={"User-Agent": "InvestIA/0.1", "Accept": "application/json"},
        )
        response.raise_for_status()
        return response.json()

    @staticmethod
    def normalize_records(payload: Any) -> list[dict[str, Any]]:
        if isinstance(payload, list):
            return payload
        if isinstance(payload, dict):
            for key in ["resultado", "resultados", "content", "data", "items"]:
                value = payload.get(key)
                if isinstance(value, list):
                    return value
            if isinstance(payload.get("_embedded"), dict):
                for value in payload["_embedded"].values():
                    if isinstance(value, list):
                        return value
        return []

    @staticmethod
    def record_text(record: dict[str, Any]) -> str:
        fields = [
            "objeto",
            "Objeto",
            "descricao",
            "descrição",
            "informacoes_gerais",
            "informacoesGerais",
            "numero_processo",
            "orgao",
            "orgaoEntidadeRazaoSocial",
        ]
        return " ".join(str(record.get(field, "")) for field in fields).lower()

    @classmethod
    def is_ai_related(cls, record: dict[str, Any]) -> bool:
        text = f" {cls.record_text(record)} "
        return any(term in text for term in AI_TERMS)

    @classmethod
    def process_records(cls, records: list[dict[str, Any]], collected_at: str) -> list[dict[str, Any]]:
        rows = []
        for index, record in enumerate(records):
            if not cls.is_ai_related(record):
                continue
            title = record.get("objeto") or record.get("Objeto") or record.get("descricao") or "Contratação pública relacionada a IA"
            rows.append(
                {
                    "id": record.get("id") or record.get("identificador") or record.get("numero_processo") or str(index),
                    "title": str(title).strip(),
                    "summary": str(record.get("informacoes_gerais") or record.get("informacoesGerais") or title).strip(),
                    "date": record.get("data_publicacao") or record.get("dataPublicacaoPncp") or record.get("dataInclusao") or "",
                    "orgao": record.get("orgao") or record.get("orgaoEntidadeRazaoSocial") or "",
                    "modality": record.get("modalidade") or record.get("modalidadeNome") or "",
                    "estimated_value": record.get("valor_estimado_total") or record.get("valorTotalEstimado") or "",
                    "source_id": cls.SOURCE_ID,
                    "source_name": cls.SOURCE_NAME,
                    "official_url": cls.OFFICIAL_URL,
                    "collected_at": collected_at,
                    "is_demo": "false",
                    "known_limitations": "Spike inicial: coleta por janela curta e filtro local por termos de IA/CT&I.",
                }
            )
        return rows

    @staticmethod
    def default_window(days: int = 2) -> tuple[str, str]:
        end = date.today()
        start = end - timedelta(days=days)
        return start.isoformat(), end.isoformat()

    def run(self, start_date: str | None = None, end_date: str | None = None) -> dict[str, Any]:
        self.ensure_dirs()
        collected_at = datetime.now(timezone.utc).isoformat()
        start_date, end_date = (start_date, end_date) if start_date and end_date else self.default_window()
        raw_openapi_path = self.raw_dir / "compras_gov_openapi.json"
        raw_licitacoes_path = self.raw_dir / "compras_gov_licitacoes.json"
        processed_path = self.processed_dir / "compras_gov_signals.csv"
        catalog_path = self.catalog_dir / "compras_gov_abertas_status.json"

        try:
            openapi = self.fetch_openapi()
            raw_openapi_path.write_text(json.dumps(openapi, ensure_ascii=False, indent=2), encoding="utf-8")
            payload = self.fetch_legacy_licitacoes(start_date, end_date)
            raw_licitacoes_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
            records = self.normalize_records(payload)
            rows = self.process_records(records, collected_at)
            fieldnames = [
                "id",
                "title",
                "summary",
                "date",
                "orgao",
                "modality",
                "estimated_value",
                "source_id",
                "source_name",
                "official_url",
                "collected_at",
                "is_demo",
                "known_limitations",
            ]
            with processed_path.open("w", encoding="utf-8", newline="") as csv_file:
                writer = csv.DictWriter(csv_file, fieldnames=fieldnames)
                writer.writeheader()
                writer.writerows(rows)
            catalog = {
                "source_id": self.SOURCE_ID,
                "source_name": self.SOURCE_NAME,
                "official_url": self.OFFICIAL_URL,
                "collection_method": "API JSON oficial de Compras.gov.br, módulo legado de licitações",
                "update_frequency": "Semanal",
                "raw_format": "json",
                "processed_format": "csv",
                "schema_version": "0.1-spike",
                "collected_at": collected_at,
                "period_start": start_date,
                "period_end": end_date,
                "processed_count": len(rows),
                "raw_file": raw_licitacoes_path.relative_to(self.data_dir).as_posix(),
                "processed_file": processed_path.relative_to(self.data_dir).as_posix(),
                "is_demo": False,
                "known_limitations": "Spike inicial com janela curta; a API pode ser lenta e o filtro textual é local.",
            }
        except requests.RequestException as error:
            catalog = {
                "source_id": self.SOURCE_ID,
                "source_name": self.SOURCE_NAME,
                "official_url": self.OFFICIAL_URL,
                "collection_method": "API JSON oficial de Compras.gov.br",
                "update_frequency": "Semanal",
                "schema_version": "0.1-spike",
                "collected_at": collected_at,
                "period_start": start_date,
                "period_end": end_date,
                "status": "failed",
                "last_error": str(error),
                "is_demo": True,
                "known_limitations": "A API de consulta demorou ou falhou nesta execução; nenhum dado simulado foi gravado como contratação real.",
            }

        catalog_path.write_text(json.dumps(catalog, ensure_ascii=False, indent=2), encoding="utf-8")
        logger.info("Saved Compras.gov.br catalog status to %s", catalog_path)
        return catalog


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Spike de coleta Compras.gov.br para sinais de demanda pública por IA.")
    parser.add_argument("--data-dir", default=str(DEFAULT_DATA_DIR), help="Diretório de saída dos dados.")
    parser.add_argument("--start-date", default=None, help="Data inicial YYYY-MM-DD.")
    parser.add_argument("--end-date", default=None, help="Data final YYYY-MM-DD.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    result = ComprasGovClient(data_dir=Path(args.data_dir)).run(args.start_date, args.end_date)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
