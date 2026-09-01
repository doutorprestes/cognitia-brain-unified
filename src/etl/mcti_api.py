import argparse
import io
import json
import logging
import re
import zipfile
from datetime import datetime, timezone
from html import unescape
from pathlib import Path
from typing import Any

import requests


logging.basicConfig(level=logging.INFO, format="%(levelname)s:%(name)s:%(message)s")
logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DATA_DIR = PROJECT_ROOT / "etl" / "data"


class MCTIAPIClient:
    SOURCE_ID = "mcti_indicadores"
    SOURCE_NAME = "MCTI - Indicadores Nacionais de CT&I"
    OFFICIAL_URL = "https://www.gov.br/mcti/pt-br/acesso-a-informacao/dados-abertos/dados-abertos/arquivos/indicadores_cti"

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

    def find_latest_zip_url(self, html: str) -> str:
        links = re.findall(r'<a[^>]+href="([^"]+\.zip)(:/view)"[^>]*>(.*)</a>', html, flags=re.I | re.S)
        candidates: list[tuple[int, str]] = []
        for href, title_html in links:
            title = re.sub(r"<[^>]+>", " ", title_html)
            title = re.sub(r"\s+", " ", unescape(title)).strip()
            match = re.search(r"(20\d{2})", f"{href} {title}")
            if match:
                candidates.append((int(match.group(1)), href.replace("/view", "")))
        if not candidates:
            raise ValueError("Nenhum ZIP oficial de indicadores CT&I foi encontrado na página do MCTI.")
        return max(candidates, key=lambda item: item[0])[1]

    def fetch_zip(self, url: str) -> bytes:
        response = requests.get(url, timeout=self.timeout, headers={"User-Agent": "InvestIA/0.1"})
        response.raise_for_status()
        return response.content

    def extract_json_payload(self, zip_bytes: bytes) -> tuple[str, Any, list[dict[str, Any]]]:
        with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zip_file:
            members = [
                {"filename": info.filename, "size": info.file_size}
                for info in zip_file.infolist()
                if not info.is_dir()
            ]
            json_members = [member["filename"] for member in members if member["filename"].lower().endswith(".json")]
            if not json_members:
                raise ValueError("ZIP oficial do MCTI não contém JSON.")
            json_name = json_members[0]
            with zip_file.open(json_name) as json_file:
                payload = json.load(json_file)
        return json_name, payload, members

    def summarize(self, payload: Any, collected_at: str) -> dict[str, Any]:
        tables = payload if isinstance(payload, list) else []
        table_counts = [len(table) for table in tables if isinstance(table, list)]
        observations = tables[1] if len(tables) > 1 and isinstance(tables[1], list) else []
        
        # Key Structural Indicators Mapping
        # DISP_NAC_PD_TOT_PCPIB: Investimento Total em P&D como % do PIB
        # PESQ_TOT_PCPIB: Pesquisadores por milhão de habitantes (ou equivalente)
        indicators = []
        for row in observations:
            ind_code = row.get("INDICADOR")
            if ind_code in {"DISP_NAC_PD_TOT_PCPIB", "DISP_NAC_CT_TOT_PCPIB"}:
                indicators.append({
                    "id": "rd_gdp_percent",
                    "code": ind_code,
                    "year": row.get("ANO"),
                    "value": row.get("VALOR"),
                    "label": "Investimento Total em P&D (% do PIB)",
                    "type": "indicator"
                })
            elif ind_code == "PESQ_TOT":
                 indicators.append({
                    "id": "total_researchers",
                    "code": ind_code,
                    "year": row.get("ANO"),
                    "value": row.get("VALOR"),
                    "label": "Total de Pesquisadores",
                    "type": "indicator"
                })

        # EBIA and PBIA Macro Strategies (Static Methodology Signals)
        macro_strategies = [
            {
                "id": "ebia-2021",
                "title": "Estratégia Brasileira de Inteligência Artificial (EBIA)",
                "date": "2021-04-06",
                "official_url": "https://www.gov.br/mcti/pt-br/acompanhe-o-mcti/transformacaodigital/inteligencia-artificial-estrategia-repositorio",
                "type": "policy_strategy",
                "summary": "Marco executivo nacional para o desenvolvimento e uso ético de IA no Brasil."
            },
            {
                "id": "pbia-2024",
                "title": "Plano Brasileiro de Inteligência Artificial (PBIA 2024-2028)",
                "date": "2024-07-30",
                "official_url": "https://www.gov.br/mcti/pt-br/acompanhe-o-mcti/transformacaodigital/inteligencia-artificial/pbia-2024-2028",
                "type": "policy_strategy",
                "summary": "Novo plano nacional focado em soberania tecnológica, infraestrutura (Lumi) e impacto social da IA."
            }
        ]

        latest_rd_gdp = None
        rd_gdp_list = [i for i in indicators if i["id"] == "rd_gdp_percent"]
        if rd_gdp_list:
            latest_rd_gdp = max(rd_gdp_list, key=lambda x: str(x["year"]))["value"]

        return {
            "source_id": self.SOURCE_ID,
            "source_name": self.SOURCE_NAME,
            "official_url": self.OFFICIAL_URL,
            "collected_at": collected_at,
            "is_demo": False,
            "indicators": indicators,
            "macro_strategies": macro_strategies,
            "rd_gdp_percent": latest_rd_gdp,
            "records_count": sum(table_counts) if table_counts else 0,
            "known_limitations": "Indicadores baseados no ZIP oficial de indicadores de CT&I do MCTI; estratégias EBIA e PBIA são marcos metodológicos.",
        }

    def run(self) -> dict[str, Any]:
        self.ensure_dirs()
        collected_at = datetime.now(timezone.utc).isoformat()
        raw_path = self.raw_dir / "mcti_indicadores.zip"
        processed_path = self.processed_dir / "mcti_indicadores.json"
        catalog_path = self.catalog_dir / "mcti_indicadores_status.json"

        try:
            page_html = self.fetch_page()
            data_url = self.find_latest_zip_url(page_html)
            zip_bytes = self.fetch_zip(data_url)
            json_name, payload, zip_members = self.extract_json_payload(zip_bytes)
            processed = self.summarize(payload, collected_at)
            
            processed.update({"data_url": data_url, "json_member": json_name, "zip_members": zip_members})
            raw_path.write_bytes(zip_bytes)
            processed_path.write_text(json.dumps(processed, ensure_ascii=False, indent=2), encoding="utf-8")
            
            catalog = {
                "source_id": self.SOURCE_ID,
                "source_name": self.SOURCE_NAME,
                "official_url": self.OFFICIAL_URL,
                "collection_method": "ZIP oficial com JSON interno + Marcos Metodológicos",
                "update_frequency": "Trimestral/Anual",
                "raw_format": "zip",
                "processed_format": "json",
                "schema_version": "1.1",
                "collected_at": collected_at,
                "processed_count": len(processed.get("indicators", [])) + len(processed.get("macro_strategies", [])),
                "is_demo": False,
                "known_limitations": processed["known_limitations"],
            }
        except (requests.RequestException, json.JSONDecodeError, ValueError, zipfile.BadZipFile) as error:
            catalog = {
                "source_id": self.SOURCE_ID,
                "source_name": self.SOURCE_NAME,
                "official_url": self.OFFICIAL_URL,
                "collection_method": "ZIP oficial com JSON interno",
                "update_frequency": "Trimestral/Anual",
                "schema_version": "1.0",
                "collected_at": collected_at,
                "status": "failed",
                "last_error": str(error),
                "is_demo": True,
                "known_limitations": "A fonte oficial não pôde ser baixada automaticamente nesta execução; nenhum valor demonstrativo foi gravado como real.",
            }

        catalog_path.write_text(json.dumps(catalog, ensure_ascii=False, indent=2), encoding="utf-8")
        logger.info("Saved MCTI catalog status to %s", catalog_path)
        return catalog


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Coleta indicadores nacionais de CT&I do MCTI.")
    parser.add_argument("--data-dir", default=str(DEFAULT_DATA_DIR), help="Diretório de saída dos dados.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    result = MCTIAPIClient(data_dir=Path(args.data_dir)).run()
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
