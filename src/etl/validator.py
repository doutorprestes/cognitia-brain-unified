import csv
import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

import pandas as pd

logging.basicConfig(level=logging.INFO, format="%(levelname)s:%(name)s:%(message)s")
logger = logging.getLogger("etl_validator")

# Essential fields for ANY signal in InvestIA
ESSENTIAL_FIELDS = {"source_id", "source_name", "official_url", "is_demo"}

# Specific schema requirements per source (min columns/keys)
SOURCE_SCHEMAS = {
    "camara_proposicoes": {
        "format": "csv",
        "required_columns": ["id", "siglaTipo", "numero", "ano", "ementa", "dataApresentacao"],
        "unique_key": ["id"],
    },
    "senado_legislativo": {
        "format": "csv",
        "required_columns": ["id", "display_label", "sigla", "numero", "ano", "ementa", "data"],
        "unique_key": ["id"],
    },
    "dou_publicacoes": {
        "format": "csv",
        "required_columns": ["date", "title", "url", "term"],
        "unique_key": ["url"],
    },
    "finep_chamadas": {
        "format": "csv",
        "required_columns": ["title", "url"],
        "unique_key": ["url"],
    },
    "cnpq_fomento": {
        "format": "json",
        "required_keys": ["source_id", "collected_at"],
    },
    "mcti_indicadores": {
        "format": "json",
        "required_keys": ["source_id", "collected_at"],
    },
    "mgi_gov360_raiox": {
        "format": "json",
        "required_keys": ["source_id", "collected_at"],
    },
}

class DataValidator:
    def __init__(self, data_dir: Path):
        self.data_dir = Path(data_dir)
        self.processed_dir = self.data_dir / "processed"

    def validate_csv(self, source_id: str, path: Path) -> Dict[str, Any]:
        schema = SOURCE_SCHEMAS.get(source_id)
        if not schema:
            return {"valid": True, "message": "No specific schema for this CSV source"}

        try:
            df = pd.read_csv(path, encoding="utf-8-sig")
            
            # Check required columns
            missing = [col for col in schema["required_columns"] if col not in df.columns]
            if missing:
                return {"valid": False, "error": f"Missing columns: {missing}"}

            # Deduplicate
            original_count = len(df)
            df = df.drop_duplicates(subset=schema["unique_key"])
            dedup_count = len(df)
            
            if original_count > dedup_count:
                logger.info(f"Fonte {source_id}: removidas {original_count - dedup_count} duplicatas.")
                df.to_csv(path, index=False, encoding="utf-8-sig")

            return {
                "valid": True,
                "record_count": dedup_count,
                "removed_duplicates": original_count - dedup_count
            }
        except Exception as e:
            return {"valid": False, "error": str(e)}

    def validate_json(self, source_id: str, path: Path) -> Dict[str, Any]:
        schema = SOURCE_SCHEMAS.get(source_id)
        if not schema:
            return {"valid": True, "message": "No specific schema for this JSON source"}

        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(data, dict):
                 return {"valid": False, "error": "JSON root must be an object"}

            missing = [key for key in schema["required_keys"] if key not in data]
            if missing:
                return {"valid": False, "error": f"Missing keys: {missing}"}

            return {"valid": True, "record_count": data.get("records_count") or data.get("datasets_count") or 1}
        except Exception as e:
            return {"valid": False, "error": str(e)}

    def run_validation(self, source_id: str) -> Dict[str, Any]:
        schema = SOURCE_SCHEMAS.get(source_id)
        if not schema:
             return {"status": "skipped", "message": f"No schema defined for {source_id}"}

        # Determine path
        # Note: some sources might have different file names, we look into SOURCE_DEFINITIONS equivalent logic or naming convention
        # For simplicity, we assume source_id matches or we check common filenames
        filename = f"{source_id}.csv" if schema["format"] == "csv" else f"{source_id}.json"
        
        # Override for specific naming mismatches if any
        if source_id == "senado_legislativo": filename = "senado_materias.csv"

        path = self.processed_dir / filename
        if not path.exists():
            return {"status": "error", "error": f"File not found: {path}"}

        logger.info(f"Validando {source_id}: {path.name}")
        if schema["format"] == "csv":
            result = self.validate_csv(source_id, path)
        else:
            result = self.validate_json(source_id, path)

        if result["valid"]:
            return {"status": "success", "record_count": result.get("record_count")}
        else:
            logger.error(f"Falha na validação de {source_id}: {result['error']}")
            return {"status": "failed", "error": result["error"]}

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", required=True)
    parser.add_argument("--data-dir", default="etl/data")
    args = parser.parse_args()
    
    validator = DataValidator(Path(args.data_dir))
    print(json.dumps(validator.run_validation(args.source)))
