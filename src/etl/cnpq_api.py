import argparse
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


class CNPqAPIClient:
    SOURCE_ID = "cnpq_fomento"
    SOURCE_NAME = "CNPq - Painel de Fomento em CT&I"
    OFFICIAL_URL = "https://www.gov.br/cnpq/pt-br/acesso-a-informacao/dados-abertos/paineis-de-dados/painel-de-fomento-em-ciencia-tecnologia-e-inovacao"
    SERVICE_URL = "https://www.gov.br/pt-br/servicos/acesso-a-dados-abertos-do-conselho-nacional-de-desenvolvimento-cientifico-e-tecnologico-cnpq"
    CKAN_SEARCH_URL = "https://dadosabertos.cnpq.br/api/3/action/package_search"

    def __init__(self, data_dir: Path = DEFAULT_DATA_DIR, timeout: int = 30):
        self.data_dir = Path(data_dir)
        self.timeout = timeout
        self.raw_dir = self.data_dir / "raw"
        self.processed_dir = self.data_dir / "processed"
        self.catalog_dir = self.data_dir / "catalog"

    def ensure_dirs(self) -> None:
        for directory in [self.raw_dir, self.processed_dir, self.catalog_dir]:
            directory.mkdir(parents=True, exist_ok=True)

    def fetch_catalog(self) -> dict[str, Any]:
        response = requests.get(
            self.CKAN_SEARCH_URL,
            params={"q": 'inteligência artificial OR ia OR "machine learning" OR fomento OR bolsas OR auxílios', "rows": 50},
            timeout=self.timeout,
            headers={"User-Agent": "InvestIA/0.1"},
        )
        response.raise_for_status()
        return response.json()

    def fetch_service_page(self) -> str:
        response = requests.get(self.SERVICE_URL, timeout=self.timeout, headers={"User-Agent": "InvestIA/0.1"})
        response.raise_for_status()
        response.encoding = response.apparent_encoding or response.encoding or "utf-8"
        return response.text

    def process_catalog(self, payload: dict[str, Any], collected_at: str) -> dict[str, Any]:
        result = payload.get("result", {})
        datasets = []
        for package in result.get("results", []):
            resources = package.get("resources", [])
            datasets.append(
                {
                    "id": package.get("id"),
                    "name": package.get("name"),
                    "title": package.get("title"),
                    "notes": package.get("notes"),
                    "resources_count": len(resources),
                    "formats": sorted({str(resource.get("format") or "").upper() for resource in resources if resource.get("format")}),
                    "resource_urls": [resource.get("url") for resource in resources if resource.get("url")],
                    "source_id": self.SOURCE_ID,
                    "source_name": self.SOURCE_NAME,
                    "official_url": self.OFFICIAL_URL,
                    "collected_at": collected_at,
                    "is_demo": False,
                }
            )
        return {
            "datasets": datasets,
            "datasets_count": len(datasets),
            "bolsas_active": None,
            "data_scope": "ckan_catalog",
            "known_limitations": "Catálogo CKAN oficial identificado; valores financeiros agregados dependem do download dos recursos CSV/Excel listados.",
            "source_id": self.SOURCE_ID,
            "source_name": self.SOURCE_NAME,
            "official_url": self.OFFICIAL_URL,
            "collected_at": collected_at,
            "is_demo": False,
        }

    def process_service_page(self, html: str, collected_at: str, ckan_error: str) -> dict[str, Any]:
        title_match = re.search(r"<h1[^>]*>(.*)</h1>", html, flags=re.I | re.S)
        title = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", unescape(title_match.group(1)))).strip() if title_match else self.SOURCE_NAME
        links = []
        for href, label_html in re.findall(r'<a[^>]+href="([^"]+)"[^>]*>(.*)</a>', html, flags=re.I | re.S):
            label = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", unescape(label_html))).strip()
            if "dados" in label.lower() or "consultar" in label.lower() or "cnpq" in href.lower():
                links.append({"label": label, "url": href})
        return {
            "source_id": self.SOURCE_ID,
            "source_name": self.SOURCE_NAME,
            "official_url": self.OFFICIAL_URL,
            "service_url": self.SERVICE_URL,
            "collected_at": collected_at,
            "is_demo": False,
            "data_scope": "official_access_metadata",
            "title": title,
            "links": links,
            "datasets_count": len(links),
            "bolsas_active": None,
            "ckan_last_error": ckan_error,
            "known_limitations": "O portal CKAN do CNPq recusou a conexão nesta execução; foi preservada a página oficial de acesso a dados abertos como metadado real da fonte, sem métricas simuladas.",
        }

    def run(self) -> dict[str, Any]:
        self.ensure_dirs()
        collected_at = datetime.now(timezone.utc).isoformat()
        raw_path = self.raw_dir / "cnpq_fomento_catalog.json"
        raw_service_path = self.raw_dir / "cnpq_dados_abertos_service.html"
        processed_path = self.processed_dir / "cnpq_fomento.json"
        catalog_path = self.catalog_dir / "cnpq_fomento_status.json"

        try:
            payload = self.fetch_catalog()
            processed = self.process_catalog(payload, collected_at)
            raw_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
            collection_method = "API CKAN oficial"
            raw_file = raw_path.relative_to(self.data_dir).as_posix()
        except requests.RequestException as error:
            html = self.fetch_service_page()
            processed = self.process_service_page(html, collected_at, str(error))
            raw_service_path.write_text(html, encoding="utf-8")
            collection_method = "Página oficial de acesso a dados abertos"
            raw_file = raw_service_path.relative_to(self.data_dir).as_posix()

        processed_path.write_text(json.dumps(processed, ensure_ascii=False, indent=2), encoding="utf-8")
        catalog = {
            "source_id": self.SOURCE_ID,
            "source_name": self.SOURCE_NAME,
            "official_url": self.OFFICIAL_URL,
            "collection_method": collection_method,
            "update_frequency": "Mensal",
            "raw_format": "json" if raw_file.endswith(".json") else "html",
            "processed_format": "json",
            "schema_version": "1.0",
            "collected_at": collected_at,
            "processed_count": processed["datasets_count"],
            "raw_file": raw_file,
            "processed_file": processed_path.relative_to(self.data_dir).as_posix(),
            "is_demo": False,
            "known_limitations": processed["known_limitations"],
        }

        catalog_path.write_text(json.dumps(catalog, ensure_ascii=False, indent=2), encoding="utf-8")
        logger.info("Saved CNPq catalog status to %s", catalog_path)
        return catalog


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Coleta catálogo oficial de dados de fomento do CNPq.")
    parser.add_argument("--data-dir", default=str(DEFAULT_DATA_DIR), help="Diretório de saída dos dados.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    result = CNPqAPIClient(data_dir=Path(args.data_dir)).run()
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
