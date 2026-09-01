"""IA Brasil — Módulo de rastreabilidade de dados.

Este módulo fornece funcionalidades para registrar e rastrear a proveniência
dos dados coletados.

Uso:
    from src.collector.core.provenance import ProvenanceTracker

    tracker = ProvenanceTracker()
    tracker.add_record(url="https://api.example.com", method="GET")
    records = tracker.get_records()
"""

from __future__ import annotations

import time
from typing import Any

from pydantic import BaseModel, Field


class ProvenanceRecord(BaseModel):
    """Registro de proveniência de dados.

    Attributes:
        url: URL da fonte de dados
        method: Método de coleta
        timestamp: Timestamp da coleta
        confidence: Nível de confiança na fonte
        metadata: Metadados adicionais
    """

    url: str
    method: str
    timestamp: float = Field(default_factory=time.time)
    confidence: float = 1.0
    metadata: dict[str, Any] = Field(default_factory=dict)


class ProvenanceTracker:
    """Classe para rastrear a proveniência de dados.

    Attributes:
        records: Lista de registros de proveniência
    """

    def __init__(self) -> None:
        self.records: list[ProvenanceRecord] = []

    def add_record(
        self,
        url: str,
        method: str,
        confidence: float = 1.0,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        """Adiciona um registro de proveniência.

        Args:
            url: URL da fonte de dados
            method: Método de coleta
            confidence: Nível de confiança na fonte (0.0 a 1.0)
            metadata: Metadados adicionais
        """
        record = ProvenanceRecord(
            url=url,
            method=method,
            confidence=confidence,
            metadata=metadata or {},
        )
        self.records.append(record)

    def get_records(self) -> list[ProvenanceRecord]:
        """Retorna todos os registros de proveniência.

        Returns:
            Lista de registros de proveniência
        """
        return self.records

    def get_record_by_url(self, url: str) -> ProvenanceRecord | None:
        """Retorna um registro de proveniência pela URL.

        Args:
            url: URL da fonte de dados

        Returns:
            Registro de proveniência ou None se não encontrado
        """
        for record in self.records:
            if record.url == url:
                return record
        return None

    def clear_records(self) -> None:
        """Limpa todos os registros de proveniência."""
        self.records = []

    def get_average_confidence(self) -> float:
        """Retorna a média de confiança de todos os registros.

        Returns:
            Média de confiança (0.0 a 1.0)
        """
        if not self.records:
            return 0.0
        total = sum(record.confidence for record in self.records)
        return total / len(self.records)

    def filter_by_confidence(self, min_confidence: float) -> list[ProvenanceRecord]:
        """Filtra registros por nível mínimo de confiança.

        Args:
            min_confidence: Nível mínimo de confiança (0.0 a 1.0)

        Returns:
            Lista de registros filtrados
        """
        return [record for record in self.records if record.confidence >= min_confidence]
