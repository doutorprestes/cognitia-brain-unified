"""IA Brasil — Parser para documentos HTML.

Este módulo fornece funcionalidades para extrair texto e metadados de documentos HTML.

Uso:
    from src.collector.core.parser.html_parser import HTMLParser

    parser = HTMLParser()
    text = parser.extract_text("<html>...</html>")
"""

from __future__ import annotations

from bs4 import BeautifulSoup


class HTMLParser:
    """Classe para extrair texto e metadados de documentos HTML.

    Attributes:
        soup: Instância do BeautifulSoup
    """

    def __init__(self) -> None:
        self.soup: BeautifulSoup | None = None

    def load(self, html_content: str) -> None:
        """Carrega conteúdo HTML.

        Args:
            html_content: Conteúdo HTML
        """
        self.soup = BeautifulSoup(html_content, "html.parser")

    def extract_text(self) -> str:
        """Extrai texto do documento HTML.

        Returns:
            Texto extraído

        Raises:
            RuntimeError: Se nenhum conteúdo HTML estiver carregado
        """
        if not self.soup:
            raise RuntimeError("No HTML content loaded")

        return self.soup.get_text(separator="\n", strip=True)

    def extract_metadata(self) -> dict[str, str]:
        """Extrai metadados do documento HTML.

        Returns:
            Dicionário com metadados

        Raises:
            RuntimeError: Se nenhum conteúdo HTML estiver carregado
        """
        if not self.soup:
            raise RuntimeError("No HTML content loaded")

        metadata = {}

        if self.soup.title:
            metadata["title"] = self.soup.title.string if self.soup.title.string else ""

        for meta in self.soup.find_all("meta"):
            name = meta.get("name")
            if isinstance(name, str) and name:
                metadata[name] = str(meta.get("content", ""))
            else:
                prop = meta.get("property")
                if isinstance(prop, str) and prop:
                    metadata[prop] = str(meta.get("content", ""))

        return metadata

    def extract_links(self) -> list[str]:
        """Extrai links do documento HTML.

        Returns:
            Lista de URLs

        Raises:
            RuntimeError: Se nenhum conteúdo HTML estiver carregado
        """
        if not self.soup:
            raise RuntimeError("No HTML content loaded")

        links: list[str] = []
        for link in self.soup.find_all("a", href=True):
            href = link["href"]
            if isinstance(href, str) and href and not href.startswith("#"):
                links.append(href)

        return links
