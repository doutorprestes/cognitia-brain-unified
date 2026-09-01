"""IA Brasil — Parser para APIs REST.

Este módulo fornece funcionalidades para extrair dados de APIs REST.

Uso:
    from src.collector.core.parser.api_parser import APIParser

    parser = APIParser()
    data = parser.parse_response(response_data)
"""

from __future__ import annotations

from typing import Any


class APIParser:
    """Classe para extrair dados de respostas de APIs REST.

    Attributes:
        data: Dados da API
    """

    def __init__(self) -> None:
        self.data: dict[str, Any] | list[Any] = {}

    def parse_response(self, response_data: dict[str, Any] | list[Any]) -> None:
        """Parseia dados de resposta de uma API.

        Args:
            response_data: Dados da resposta da API
        """
        self.data = response_data

    def get_data(self) -> dict[str, Any] | list[Any]:
        """Retorna os dados da API.

        Returns:
            Dados da API
        """
        return self.data

    def get_paginated_data(
        self,
        response_data: dict[str, Any],
        data_key: str = "results",
        next_key: str = "next",
    ) -> list[Any]:
        """Extrai dados paginados de uma resposta de API.

        Args:
            response_data: Dados da resposta da API
            data_key: Chave para os dados na resposta
            next_key: Chave para a URL da próxima página

        Returns:
            Lista de itens de todas as páginas
        """
        items: list[Any] = []
        current_data: Any = response_data

        while current_data:
            if isinstance(current_data, dict) and data_key in current_data:
                items.extend(current_data[data_key])
                current_data = current_data.get(next_key)
            else:
                break

        return items

    def extract_field(
        self,
        field_path: str,
        default: Any = None,
    ) -> Any:
        """Extrai um campo específico dos dados da API.

        Args:
            field_path: Caminho do campo (ex: "data.items.0.name")
            default: Valor padrão se o campo não existir

        Returns:
            Valor do campo ou default
        """
        keys = field_path.split(".")
        current = self.data

        for key in keys:
            if isinstance(current, dict) and key in current:
                current = current[key]
            elif isinstance(current, list) and key.isdigit():
                index = int(key)
                if 0 <= index < len(current):
                    current = current[index]
                else:
                    return default
            else:
                return default

        return current if current is not None else default
