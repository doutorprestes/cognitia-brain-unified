"""IA Brasil — Módulo de extração estruturada de dados.

Este módulo fornece funcionalidades para extrair dados estruturados
de diferentes formatos de documento.

Uso:
    from src.collector.core.extractor import DataExtractor

    extractor = DataExtractor()
    structured_data = extractor.extract_from_text(text_data)
"""

from __future__ import annotations

import re
from datetime import datetime
from typing import Any

from loguru import logger


class DataExtractor:
    """Classe para extrair dados estruturados de texto.

    Attributes:
        patterns: Dicionário de padrões de expressão regular
    """

    def __init__(self) -> None:
        self.patterns = {
            "date": r"\d{2}/\d{2}/\d{4}",
            "cnpj": r"\d{2}\.\d{3}\.\d{3}/\d{4}-\d{2}",
            "cpf": r"\d{3}\.\d{3}\.\d{3}-\d{2}",
            "money": r"R\$\s?\d{1,3}(?:\.\d{3})*(?:,\d{2})?",
            "email": r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}",
            "phone": r"\(\d{2}\)\s?\d{4,5}-\d{4}",
            "url": r"https?://[^\s]+",
        }

    def extract_from_text(
        self,
        text: str,
        pattern_name: str,
    ) -> list[str]:
        """Extrai dados de texto usando um padrão específico.

        Args:
            text: Texto de entrada
            pattern_name: Nome do padrão a ser usado

        Returns:
            Lista de strings correspondentes ao padrão
        """
        if pattern_name not in self.patterns:
            logger.warning(f"Unknown pattern: {pattern_name}")
            return []

        pattern = self.patterns[pattern_name]
        return re.findall(pattern, text)

    def extract_dates(self, text: str) -> list[str]:
        """Extrai datas do texto.

        Args:
            text: Texto de entrada

        Returns:
            Lista de datas no formato DD/MM/YYYY
        """
        return self.extract_from_text(text, "date")

    def extract_cnpj(self, text: str) -> list[str]:
        """Extrai CNPJs do texto.

        Args:
            text: Texto de entrada

        Returns:
            Lista de CNPJs
        """
        return self.extract_from_text(text, "cnpj")

    def extract_cpf(self, text: str) -> list[str]:
        """Extrai CPFs do texto.

        Args:
            text: Texto de entrada

        Returns:
            Lista de CPFs
        """
        return self.extract_from_text(text, "cpf")

    def extract_money(self, text: str) -> list[str]:
        """Extrai valores monetários do texto.

        Args:
            text: Texto de entrada

        Returns:
            Lista de valores monetários
        """
        return self.extract_from_text(text, "money")

    def extract_emails(self, text: str) -> list[str]:
        """Extrai emails do texto.

        Args:
            text: Texto de entrada

        Returns:
            Lista de emails
        """
        return self.extract_from_text(text, "email")

    def extract_phones(self, text: str) -> list[str]:
        """Extrai telefones do texto.

        Args:
            text: Texto de entrada

        Returns:
            Lista de telefones
        """
        return self.extract_from_text(text, "phone")

    def extract_urls(self, text: str) -> list[str]:
        """Extrai URLs do texto.

        Args:
            text: Texto de entrada

        Returns:
            Lista de URLs
        """
        return self.extract_from_text(text, "url")

    def extract_structured_data(
        self,
        text: str,
        schema: dict[str, str],
    ) -> dict[str, Any]:
        """Extrai dados estruturados com base em um esquema.

        Args:
            text: Texto de entrada
            schema: Esquema de extração (ex: {"date": "date", "value": "money"})

        Returns:
            Dicionário com dados estruturados
        """
        result = {}
        for field, pattern_name in schema.items():
            matches = self.extract_from_text(text, pattern_name)
            if matches:
                result[field] = matches[0] if len(matches) == 1 else matches
        return result

    def normalize_date(self, date_str: str) -> str | None:
        """Normaliza uma data para o formato ISO.

        Args:
            date_str: Data no formato DD/MM/YYYY

        Returns:
            Data no formato ISO (YYYY-MM-DD) ou None se inválida
        """
        try:
            date_obj = datetime.strptime(date_str, "%d/%m/%Y")
            return date_obj.strftime("%Y-%m-%d")
        except ValueError:
            return None

    def normalize_money(self, money_str: str) -> float | None:
        """Normaliza um valor monetário para float.

        Args:
            money_str: Valor monetário (ex: "R$ 1.234,56")

        Returns:
            Valor como float ou None se inválido
        """
        try:
            cleaned = money_str.replace("R$", "").replace(".", "").replace(",", ".")
            return float(cleaned.strip())
        except ValueError:
            return None
