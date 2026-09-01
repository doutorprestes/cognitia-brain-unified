import argparse
import json
import logging
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional
try:
    from etl.validator import DataValidator
except ImportError:
    from validator import DataValidator

logging.basicConfig(level=logging.INFO, format="%(levelname)s:%(name)s:%(message)s")
logger = logging.getLogger("etl_orchestrator")

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DATA_DIR = PROJECT_ROOT / "etl" / "data"

# Mapping source_id to script filename
SOURCE_SCRIPTS = {
    "camara_proposicoes": "camara_api.py",
    "senado_legislativo": "senado_api.py",
    "cnpq_fomento": "cnpq_api.py",
    "mcti_indicadores": "mcti_api.py",
    "finep_chamadas": "finep_api.py",
    "dou_publicacoes": "dou_api.py",
    "mgi_gov360_raiox": "mgi_gov360_api.py",
    "compras_gov_br": "compras_gov_api.py",
}

class ETLOrchestrator:
    def __init__(self, data_dir: Path = DEFAULT_DATA_DIR):
        self.data_dir = Path(data_dir)
        self.catalog_dir = self.data_dir / "catalog"
        self.consolidated_path = self.catalog_dir / "sources_status.json"
        self.scripts_dir = PROJECT_ROOT / "etl"
        self.validator = DataValidator(data_dir=self.data_dir)

    def run_source(self, source_id: str, extra_args: List[str]) -> Dict[str, Any]:
        script_name = SOURCE_SCRIPTS.get(source_id)
        if not script_name:
            logger.error(f"Fonte desconhecida: {source_id}")
            return {"source_id": source_id, "status": "failed", "error": "Unknown source"}

        script_path = self.scripts_dir / script_name
        if not script_path.exists():
            logger.error(f"Script não encontrado: {script_path}")
            return {"source_id": source_id, "status": "failed", "error": "Script missing"}

        logger.info(f"Iniciando coleta: {source_id}...")
        start_time = datetime.now(timezone.utc)
        
        cmd = [sys.executable, str(script_path), "--data-dir", str(self.data_dir)]
        cmd.extend(extra_args)

        try:
            result = subprocess.run(cmd, capture_output=True, text=True, check=False)
            end_time = datetime.now(timezone.utc)
            duration = (end_time - start_time).total_seconds()

            if result.returncode == 0:
                logger.info(f"Sucesso: {source_id} em {duration:.2f}s")
                # Try to parse summary from stdout
                try:
                    summary = json.loads(result.stdout)
                    
                    # Validation step
                    validation = self.validator.run_validation(source_id)
                    if validation["status"] == "failed":
                        return {
                            "source_id": source_id,
                            "status": "failed",
                            "error": f"Validation failed: {validation.get('error')}",
                            "summary": summary
                        }
                    
                    return {
                        "source_id": source_id,
                        "status": "success",
                        "duration": duration,
                        "summary": summary,
                        "validation": validation
                    }
                except json.JSONDecodeError:
                    return {
                        "source_id": source_id,
                        "status": "success",
                        "duration": duration,
                        "raw_output": result.stdout
                    }
            else:
                logger.error(f"Erro ao rodar {source_id}: {result.stderr}")
                return {
                    "source_id": source_id,
                    "status": "failed",
                    "error": result.stderr,
                    "exit_code": result.returncode
                }
        except Exception as e:
            logger.exception(f"Exceção ao rodar {source_id}")
            return {"source_id": source_id, "status": "failed", "error": str(e)}

    def consolidate_catalog(self) -> None:
        logger.info("Consolidando catálogo de fontes...")
        consolidated = {
            "last_orchestration_at": datetime.now(timezone.utc).isoformat(),
            "sources": {}
        }

        for source_id in SOURCE_SCRIPTS.keys():
            status_file = self.catalog_dir / f"{source_id}_status.json"
            if status_file.exists():
                try:
                    consolidated["sources"][source_id] = json.loads(status_file.read_text(encoding="utf-8"))
                except Exception as e:
                    logger.warning(f"Erro ao ler status de {source_id}: {e}")

        self.catalog_dir.mkdir(parents=True, exist_ok=True)
        self.consolidated_path.write_text(json.dumps(consolidated, indent=2, ensure_ascii=False), encoding="utf-8")
        logger.info(f"Catálogo consolidado em: {self.consolidated_path}")

    def run_all(self, extra_args: List[str]) -> None:
        results = []
        for source_id in SOURCE_SCRIPTS.keys():
            results.append(self.run_source(source_id, extra_args))
        
        self.consolidate_catalog()
        
        successes = sum(1 for r in results if r["status"] == "success")
        failures = sum(1 for r in results if r["status"] == "failed")
        logger.info(f"Orquestração finalizada. Sucessos: {successes}, Falhas: {failures}")

def main():
    parser = argparse.ArgumentParser(description="Orquestrador de ETL do InvestIA")
    parser.add_argument("--all", action="store_true", help="Rodar todos os conectores")
    parser.add_argument("--source", type=str, help="Rodar um conector específico")
    parser.add_argument("--data-dir", type=str, default=str(DEFAULT_DATA_DIR), help="Diretório de dados")
    parser.add_argument("--consolidate", action="store_true", help="Apenas consolidar o catálogo")
    
    args, unknown = parser.parse_known_args()

    orchestrator = ETLOrchestrator(data_dir=Path(args.data_dir))

    if args.consolidate:
        orchestrator.consolidate_catalog()
    elif args.all:
        orchestrator.run_all(unknown)
    elif args.source:
        orchestrator.run_source(args.source, unknown)
        orchestrator.consolidate_catalog()
    else:
        parser.print_help()

if __name__ == "__main__":
    main()
