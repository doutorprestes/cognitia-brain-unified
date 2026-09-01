"""IA Brasil — PBIA Parser Module.

Módulo responsável por:
1. Parsing do documento oficial do PBIA (PDF ou texto)
2. Extração de entidades do domínio
3. Ingestão async no banco de dados

Estrutura:
    parser.py      - Extração de entidades do documento
    ingestion.py  - Persistência async no banco
    schemas.py    - Schemas Pydantic para validação
"""

from src.modules.pbia_parser.ingestion import ingest_pbia
from src.modules.pbia_parser.parser import parse_pbia_document
from src.modules.pbia_parser.schemas import IngestionReport

__all__ = ["IngestionReport", "ingest_pbia", "parse_pbia_document"]
