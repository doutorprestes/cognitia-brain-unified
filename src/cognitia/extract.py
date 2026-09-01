"""Extração de texto de arquivos locais (.txt, .md, .pdf, .html)."""

from __future__ import annotations

from pathlib import Path
from typing import Optional


def extract_text(path: Path | str) -> Optional[str]:
    try:
        path_str = str(path)
        if path_str.startswith("http://") or path_str.startswith("https://"):
            return _read_url(path_str)
            
        p = Path(path)
        suffix = p.suffix.lower()
        if suffix in {".txt", ".md"}:
            return _read_text(p)
        if suffix == ".pdf":
            return _read_pdf(p)
        if suffix in {".html", ".htm"}:
            return _read_html(p)
    except Exception as e:  # noqa: BLE001
        # Falha silenciosa controlada pelo caller; não derruba o pipeline.
        return None
    return None

def _read_url(url: str) -> str:
    import requests
    try:
        from bs4 import BeautifulSoup  # type: ignore[import-untyped]
    except ImportError as exc:
        raise RuntimeError(
            "beautifulsoup4 não instalado."
        ) from exc
        
    r = requests.get(url, timeout=15)
    r.raise_for_status()
    soup = BeautifulSoup(r.text, "html.parser")
    for tag in soup(["script", "style", "nav", "header", "footer"]):
        tag.decompose()
    return soup.get_text(separator="\n", strip=True)


def _read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="ignore")


def _read_pdf(path: Path) -> str:
    try:
        import pdfplumber  # type: ignore[import-untyped]
    except ImportError as exc:
        raise RuntimeError(
            "pdfplumber não instalado. Rode: pip install pdfplumber"
        ) from exc

    parts: list[str] = []
    with pdfplumber.open(str(path)) as pdf:
        for page in pdf.pages:
            txt = page.extract_text() or ""
            if txt:
                parts.append(txt)
    return "\n".join(parts)


def _read_html(path: Path) -> str:
    try:
        from bs4 import BeautifulSoup  # type: ignore[import-untyped]
    except ImportError as exc:
        raise RuntimeError(
            "beautifulsoup4 não instalado. Rode: pip install beautifulsoup4"
        ) from exc

    html = path.read_text(encoding="utf-8", errors="ignore")
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "nav", "header", "footer"]):
        tag.decompose()
    return soup.get_text(separator="\n", strip=True)


_nlp = None

def get_nlp():
    global _nlp
    if _nlp is None:
        import spacy  # type: ignore[import-untyped]
        try:
            _nlp = spacy.load("pt_core_news_sm")
        except OSError:
            raise RuntimeError(
                "Modelo spacy não encontrado. Rode: python -m spacy download pt_core_news_sm"
            )
    return _nlp

def chunk_text(text: str, max_chars: int = 1500) -> list[str]:
    """Quebra o texto em chunks semânticos preservando frases.

    O spaCy tem limite de ~1M chars por documento; textos grandes (ex: PDFs
    de 20+ MB) estouram esse limite. Processamos em blocos de ate 900k chars.
    """
    nlp = get_nlp()

    # Pré-divide em blocos seguros para o spaCy
    BLOCK = 900_000
    blocks = [text[i : i + BLOCK] for i in range(0, len(text), BLOCK)] or [""]

    chunks: list[str] = []
    current_chunk: list[str] = []
    current_len = 0

    for block in blocks:
        doc = nlp(block)
        for sent in doc.sents:
            sent_text = sent.text.strip()
            if not sent_text:
                continue
            if current_len + len(sent_text) > max_chars and current_chunk:
                chunks.append(" ".join(current_chunk))
                current_chunk = []
                current_len = 0
            current_chunk.append(sent_text)
            current_len += len(sent_text) + 1  # +1 for space

    if current_chunk:
        chunks.append(" ".join(current_chunk))

    return chunks
