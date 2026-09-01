import argparse
import csv
import json
import logging
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.parse import quote

import requests

logging.basicConfig(level=logging.INFO, format="%(levelname)s:%(name)s:%(message)s")
logger = logging.getLogger("senado_api")

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DATA_DIR = PROJECT_ROOT / "etl" / "data"

SEARCH_TERMS = [
    "inteligencia artificial",
    "inteligência artificial",
    "algoritmo",
    "machine learning",
    "aprendizado de máquina",
    "ciência e tecnologia",
]

MATCH_TERMS = [
    "inteligencia artificial",
    "inteligência artificial",
    "ia",
    "algoritmo",
    "machine learning",
    "dados",
    "inovação",
    "ciência",
    "tecnologia",
]

PROCESSED_FIELDS = [
    "id",
    "display_label",
    "sigla",
    "numero",
    "ano",
    "ementa",
    "primary_author",
    "date",
    "official_url",
    "url",
    "keywords_matched",
    "source_id",
    "source_name",
    "collected_at",
    "is_demo",
    "status_legislativo",
]

@dataclass(frozen=True)
class RunSummary:
    collected_at: str
    raw_count: int
    processed_count: int
    raw_path: Path
    processed_path: Path
    catalog_path: Path

class SenadoAPIClient:
    BASE_URL = "https://legis.senado.leg.br/dadosabertos/materia/pesquisa/lista"
    SOURCE_ID = "senado_legislativo"
    SOURCE_NAME = "Senado Federal - Dados Abertos"

    def __init__(self, data_dir: Path = DEFAULT_DATA_DIR, timeout: int = 30):
        self.data_dir = Path(data_dir)
        self.timeout = timeout
        self.raw_dir = self.data_dir / "raw"
        self.processed_dir = self.data_dir / "processed"
        self.catalog_dir = self.data_dir / "catalog"

    def fetch_term(self, term: str) -> List[Dict[str, Any]]:
        logger.info(f"Buscando termo no Senado: {term}")
        try:
            response = requests.get(
                f"{self.BASE_URL}?termo={quote(term)}",
                headers={"Accept": "application/json"},
                timeout=self.timeout,
            )
            response.raise_for_status()
            payload = response.json()
            materias = payload.get("PesquisaBasicaMateria", {}).get("Materias", {}).get("Materia", [])
            if isinstance(materias, dict):
                return [materias]
            return materias if isinstance(materias, list) else []
        except Exception as e:
            logger.error(f"Erro ao buscar termo '{term}': {e}")
            return []

    def _matched_keywords(self, materia: Dict[str, Any]) -> List[str]:
        searchable = " ".join([
            str(materia.get("Ementa", "")),
            str(materia.get("DescricaoIdentificacao", "")),
            str(materia.get("Autor", "")),
        ]).casefold()
        return [term for term in MATCH_TERMS if term.casefold() in searchable]

    def process_records(self, raw_records: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        processed: Dict[str, Dict[str, Any]] = {}
        collected_at = datetime.now(timezone.utc).isoformat()
        
        for record in raw_records:
            matches = self._matched_keywords(record)
            if not matches:
                continue
                
            codigo = str(record.get("Codigo", "")).strip()
            if not codigo or codigo in processed:
                continue
                
            processed[codigo] = {
                "id": codigo,
                "display_label": str(record.get("DescricaoIdentificacao", "")),
                "sigla": str(record.get("Sigla", "")),
                "numero": str(record.get("Numero", "")),
                "ano": str(record.get("Ano", "")),
                "ementa": str(record.get("Ementa", "")),
                "primary_author": str(record.get("Autor", "")),
                "date": str(record.get("Data", "")),
                "official_url": str(record.get("UrlDetalheMateria", "")),
                "url": str(record.get("UrlDetalheMateria", "")),
                "keywords_matched": ";".join(matches),
                "source_id": self.SOURCE_ID,
                "source_name": self.SOURCE_NAME,
                "collected_at": collected_at,
                "is_demo": False,
                "status_legislativo": "Consulte URL oficial para tramitação atualizada",
            }
        
        return sorted(processed.values(), key=lambda x: x["date"], reverse=True)

    def run(self, terms: Optional[List[str]] = None) -> RunSummary:
        self.raw_dir.mkdir(parents=True, exist_ok=True)
        self.processed_dir.mkdir(parents=True, exist_ok=True)
        self.catalog_dir.mkdir(parents=True, exist_ok=True)
        
        terms = terms or SEARCH_TERMS
        all_raw: List[Dict[str, Any]] = []
        raw_payloads: Dict[str, Any] = {}
        
        for term in terms:
            records = self.fetch_term(term)
            raw_payloads[term] = records
            all_raw.extend(records)
            time.sleep(0.2) # Friendly to API

        processed = self.process_records(all_raw)
        
        raw_path = self.raw_dir / "senado_materias.json"
        processed_path = self.processed_dir / "senado_materias.csv"
        catalog_path = self.catalog_dir / "senado_legislativo_status.json"
        
        raw_path.write_text(json.dumps(raw_payloads, ensure_ascii=False, indent=2), encoding="utf-8")
        
        with processed_path.open("w", encoding="utf-8-sig", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=PROCESSED_FIELDS)
            writer.writeheader()
            writer.writerows(processed)
            
        collected_at = datetime.now(timezone.utc).isoformat()
        catalog_payload = {
            "source_id": self.SOURCE_ID,
            "source_name": self.SOURCE_NAME,
            "official_url": self.BASE_URL,
            "collection_method": "API JSON por termo de busca",
            "schema_version": "1.1",
            "collected_at": collected_at,
            "raw_count": len(all_raw),
            "processed_count": len(processed),
            "known_limitations": "Busca restrita a termos de IA/CT&I para reduzir ruído; datas históricas dependem da cobertura da pesquisa por termo.",
        }
        catalog_path.write_text(json.dumps(catalog_payload, ensure_ascii=False, indent=2), encoding="utf-8")
        
        return RunSummary(
            collected_at=collected_at,
            raw_count=len(all_raw),
            processed_count=len(processed),
            raw_path=raw_path,
            processed_path=processed_path,
            catalog_path=catalog_path
        )

def main():
    parser = argparse.ArgumentParser(description="Coleta matérias do Senado relacionadas a IA/CT&I.")
    parser.add_argument("--data-dir", type=str, default=str(DEFAULT_DATA_DIR), help="Diretório de dados")
    parser.add_argument("--term", action="append", dest="terms", help="Termo de busca adicional.")
    args = parser.parse_args()
    
    client = SenadoAPIClient(data_dir=Path(args.data_dir))
    summary = client.run(terms=args.terms)
    
    print(json.dumps({
        "collected_at": summary.collected_at,
        "raw_count": summary.raw_count,
        "processed_count": summary.processed_count,
    }, indent=2))

if __name__ == "__main__":
    main()
