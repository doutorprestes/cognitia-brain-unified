"""IA Brasil — Parser para documentos JSON.

Este módulo fornece funcionalidades para extrair dados de arquivos JSON.

Uso:
    from src.collector.core.parser.json_parser import JSONParser

    parser = JSONParser()
    data = parser.parse("path/to/file.json")
"""

from __future__ import annotations

import json
from typing import Any

from loguru import logger


class JSONParser:
    """Classe para extrair dados de arquivos JSON.

    Attributes:
        data: Dados do JSON
    """

    def __init__(self) -> None:
        self.data: dict[str, Any] | list[Any] = {}

    def parse(self, file_path: str) -> None:
        """Parseia um arquivo JSON.

        Args:
            file_path: Caminho para o arquivo JSON

        Raises:
            FileNotFoundError: Se o arquivo não existir
            json.JSONDecodeError: Se o arquivo não for um JSON válido
        """
        try:
            with open(file_path, encoding="utf-8") as file:
                self.data = json.load(file)
        except FileNotFoundError:
            logger.error(f"File not found: {file_path}")
            raise
        except json.JSONDecodeError:
            logger.error(f"Invalid JSON file: {file_path}")
            raise

    def parse_from_string(self, json_content: str) -> None:
        """Parseia conteúdo JSON a partir de uma string.

        Args:
            json_content: Conteúdo JSON

        Raises:
            json.JSONDecodeError: Se o conteúdo não for um JSON válido
        """
        try:
            self.data = json.loads(json_content)
        except json.JSONDecodeError:
            logger.error("Invalid JSON content")
            raise

    def get_data(self) -> dict[str, Any] | list[Any]:
        """Retorna os dados do JSON.

        Returns:
            Dados do JSON
        """
        return self.data

    def get_keys(self) -> list[str]:
        """Retorna as chaves do JSON (se for um dicionário).

        Returns:
            Lista de chaves

        Raises:
            TypeError: Se os dados não forem um dicionário
        """
        if isinstance(self.data, dict):
            return list(self.data.keys())
        raise TypeError("Data is not a dictionary")

    def get_value(self, key: str) -> Any:
        """Retorna o valor de uma chave do JSON.

        Args:
            key: Chave do JSON

        Returns:
            Valor da chave

        Raises:
            TypeError: Se os dados não forem um dicionário
            KeyError: Se a chave não existir
        """
        if isinstance(self.data, dict):
            return self.data[key]
        raise TypeError("Data is not a dictionary")
