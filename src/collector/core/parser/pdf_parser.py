"""IA Brasil — Parser para documentos PDF.

Este módulo fornece funcionalidades para extrair texto e metadados de documentos PDF.

Uso:
    from src.collector.core.parser.pdf_parser import PDFParser

    parser = PDFParser()
    text = parser.extract_text("/path/to/file.pdf")
"""

from __future__ import annotations

import io
from typing import Any

import pypdf
from loguru import logger


class PDFParser:
    """Classe para extrair texto e metadados de documentos PDF.

    Attributes:
        reader: Instância do PyPDF2 PdfReader
    """

    def __init__(self) -> None:
        self.reader: pypdf.PdfReader | None = None

    def load(self, file_path: str) -> None:
        """Carrega um arquivo PDF.

        Args:
            file_path: Caminho para o arquivo PDF

        Raises:
            FileNotFoundError: Se o arquivo não existir
            pypdf.errors.PdfReadError: Se o arquivo não for um PDF válido
        """
        try:
            with open(file_path, "rb") as file:
                self.reader = pypdf.PdfReader(file)
        except FileNotFoundError:
            logger.error(f"File not found: {file_path}")
            raise
        except pypdf.errors.PdfReadError:
            logger.error(f"Invalid PDF file: {file_path}")
            raise

    def load_from_bytes(self, data: bytes) -> None:
        """Carrega um PDF a partir de bytes.

        Args:
            data: Bytes do arquivo PDF

        Raises:
            pypdf.errors.PdfReadError: Se os bytes não formarem um PDF válido
        """
        try:
            self.reader = pypdf.PdfReader(io.BytesIO(data))
        except pypdf.errors.PdfReadError:
            logger.error("Invalid PDF data")
            raise

    def extract_text(self, page_numbers: list[int] | None = None) -> str:
        """Extrai texto de páginas específicas ou de todo o documento.

        Args:
            page_numbers: Lista de números de página (1-indexed)

        Returns:
            Texto extraído

        Raises:
            RuntimeError: Se nenhum arquivo PDF estiver carregado
        """
        if not self.reader:
            raise RuntimeError("No PDF file loaded")

        text = ""
        pages = page_numbers if page_numbers else range(len(self.reader.pages))

        for page_num in pages:
            if page_num < 1 or page_num > len(self.reader.pages):
                logger.warning(f"Page number {page_num} out of range")
                continue

            page = self.reader.pages[page_num - 1]
            text += page.extract_text() + "\n"

        return text.strip()

    def extract_metadata(self) -> dict[str, Any]:
        """Extrai metadados do documento PDF.

        Returns:
            Dicionário com metadados

        Raises:
            RuntimeError: Se nenhum arquivo PDF estiver carregado
        """
        if not self.reader:
            raise RuntimeError("No PDF file loaded")

        metadata = self.reader.metadata
        return {
            "title": metadata.title if metadata and metadata.title else "",
            "author": metadata.author if metadata and metadata.author else "",
            "creator": metadata.creator if metadata and metadata.creator else "",
            "producer": metadata.producer if metadata and metadata.producer else "",
            "subject": metadata.subject if metadata and metadata.subject else "",
            "num_pages": len(self.reader.pages),
        }

    def get_page_count(self) -> int:
        """Retorna o número de páginas do documento.

        Returns:
            Número de páginas

        Raises:
            RuntimeError: Se nenhum arquivo PDF estiver carregado
        """
        if not self.reader:
            raise RuntimeError("No PDF file loaded")
        return len(self.reader.pages)
