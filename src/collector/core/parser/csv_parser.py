"""IA Brasil — Parser para documentos CSV.

Este módulo fornece funcionalidades para extrair dados de arquivos CSV.

Uso:
    from src.collector.core.parser.csv_parser import CSVParser

    parser = CSVParser()
    data = parser.parse("path/to/file.csv")
"""

from __future__ import annotations

import csv
from typing import Any

from loguru import logger


class CSVParser:
    """Classe para extrair dados de arquivos CSV.

    Attributes:
        data: Dados do CSV
        headers: Cabeçalhos do CSV
    """

    def __init__(self) -> None:
        self.data: list[dict[str, Any]] = []
        self.headers: list[str] = []

    def parse(self, file_path: str, delimiter: str = ",") -> None:
        """Parseia um arquivo CSV.

        Args:
            file_path: Caminho para o arquivo CSV
            delimiter: Delimitador do CSV

        Raises:
            FileNotFoundError: Se o arquivo não existir
            csv.Error: Se o arquivo não for um CSV válido
        """
        try:
            with open(file_path, encoding="utf-8") as file:
                reader = csv.DictReader(file, delimiter=delimiter)
                self.headers = list(reader.fieldnames) if reader.fieldnames else []
                self.data = list(reader)
        except FileNotFoundError:
            logger.error(f"File not found: {file_path}")
            raise
        except csv.Error:
            logger.error(f"Invalid CSV file: {file_path}")
            raise

    def parse_from_string(self, csv_content: str, delimiter: str = ",") -> None:
        """Parseia conteúdo CSV a partir de uma string.

        Args:
            csv_content: Conteúdo CSV
            delimiter: Delimitador do CSV

        Raises:
            csv.Error: Se o conteúdo não for um CSV válido
        """
        try:
            lines = csv_content.strip().split("\n")
            reader = csv.DictReader(lines, delimiter=delimiter)
            self.headers = list(reader.fieldnames) if reader.fieldnames else []
            self.data = list(reader)
        except csv.Error:
            logger.error("Invalid CSV content")
            raise

    def get_data(self) -> list[dict[str, Any]]:
        """Retorna os dados do CSV.

        Returns:
            Lista de dicionários com os dados
        """
        return self.data

    def get_headers(self) -> list[str]:
        """Retorna os cabeçalhos do CSV.

        Returns:
            Lista de cabeçalhos
        """
        return self.headers

    def get_row_count(self) -> int:
        """Retorna o número de linhas do CSV.

        Returns:
            Número de linhas
        """
        return len(self.data)
