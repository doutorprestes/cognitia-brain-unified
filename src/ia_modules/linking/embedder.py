"""Interface de embeddings para vinculação automática — IA Brasil.

Implementa embeddings leves via TF-IDF (sem GPU, sem transformers).
Fallback para word overlap quando sklearn não disponível.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, cast

import numpy as np
from loguru import logger

if TYPE_CHECKING:
    from numpy.typing import NDArray

# Termos-chave do PBIA para peso extra
PBIA_KEYWORDS: list[str] = [
    "inteligência artificial",
    "ia",
    "pb",
    "ct",
    "sncti",
    "finep",
    "bndes",
    "fndct",
    "ciência",
    "tecnologia",
    "inovação",
    "pesquisa",
    "desenvolvimento",
    "infraestrutura",
    "dados abertos",
    "governo digital",
    "transformação digital",
    "startup",
    "ecossistema",
    "capacitação",
]

_STOP_WORDS_PT: set[str] = {
    "a",
    "o",
    "e",
    "de",
    "do",
    "da",
    "dos",
    "das",
    "em",
    "no",
    "na",
    "nos",
    "nas",
    "por",
    "para",
    "com",
    "sem",
    "sob",
    "sobre",
    "entre",
    "até",
    "desde",
    "após",
    "ou",
    "mas",
    "que",
    "se",
    "como",
    "mais",
    "muito",
    "já",
    "está",
    "são",
    "foi",
    "ser",
    "ter",
    "há",
    "um",
    "uma",
    "uns",
    "umas",
    "os",
    "as",
    "este",
    "esta",
    "esse",
    "essa",
    "aquele",
    "aquela",
    "isto",
    "isso",
    "aquilo",
    "mesmo",
    "próprio",
    "todo",
    "toda",
    "todos",
    "todas",
    "outro",
    "outra",
    "outros",
    "outras",
    "pode",
    "podem",
    "poderá",
    "deve",
    "devem",
    "deverá",
    "vai",
    "vão",
    "foi",
    "foram",
    "sendo",
    "era",
    "eram",
    "será",
    "serão",
    "não",
    "sim",
    "também",
    "ainda",
    "apenas",
    "quando",
    "onde",
    "quem",
    "qual",
    "quais",
    "quanto",
    "quantos",
    "quanta",
    "quantas",
    "cada",
    "todo",
    "algum",
    "alguma",
    "nenhum",
    "nenhuma",
    "todos",
    "todas",
    "ambos",
    "ambas",
}


def _tokenize(text: str) -> list[str]:
    """Tokeniza texto em palavras minúsculas, removendo stop words e pontuação."""
    text_lower = text.lower()
    tokens = re.findall(r"[a-záàãâéêíóôõúüç]+", text_lower)
    return [t for t in tokens if t not in _STOP_WORDS_PT and len(t) > 2]


class Embedder:
    """Gera embeddings via TF-IDF para comparação textual."""

    def __init__(self) -> None:
        self._vectorizer: object | None = None
        self._corpus_vectors: NDArray[np.float64] | None = None
        self._corpus_ids: list[str] = []
        self._fitted = False

    def fit(self, texts: list[str], ids: list[str]) -> None:
        """Ajusta o vectorizer TF-IDF no corpus e armalena os vetores.

        Args:
            texts: Lista de textos para ajustar o vectorizer.
            ids: IDs correspondentes a cada texto.
        """
        try:
            from sklearn.feature_extraction.text import TfidfVectorizer

            self._vectorizer = TfidfVectorizer(
                tokenizer=_tokenize,
                token_pattern=None,
                max_features=5000,
                sublinear_tf=True,
            )
            assert isinstance(self._vectorizer, TfidfVectorizer)
            matrix = self._vectorizer.fit_transform(texts)
            self._corpus_vectors = matrix.toarray()
            self._corpus_ids = ids
            self._fitted = True
            logger.info(f"Embedder ajustado com {len(texts)} textos, {len(ids)} documentos")
        except ImportError:
            logger.warning("sklearn não disponível, usando fallback word overlap")
            self._fitted = False

    def embed(self, text: str) -> NDArray[np.float64]:
        """Gera embedding de um texto.

        Args:
            text: Texto para gerar embedding.

        Returns:
            Vetor numpy representando o embedding.
        """
        if self._fitted and self._vectorizer is not None:
            from sklearn.feature_extraction.text import TfidfVectorizer

            assert isinstance(self._vectorizer, TfidfVectorizer)
            return cast("NDArray[np.float64]", self._vectorizer.transform([text]).toarray()[0])

        # Fallback: representação de word overlap
        tokens = _tokenize(text)
        vec = np.zeros(len(PBIA_KEYWORDS), dtype=np.float64)
        for i, kw in enumerate(PBIA_KEYWORDS):
            if kw in tokens or kw in text.lower():
                vec[i] = 1.0
        return vec

    def similarity(self, v1: NDArray[np.float64], v2: NDArray[np.float64]) -> float:
        """Calcula similaridade cosine entre dois vetores.

        Args:
            v1: Primeiro vetor.
            v2: Segundo vetor.

        Returns:
            Similaridade entre 0.0 e 1.0.
        """
        norm1 = np.linalg.norm(v1)
        norm2 = np.linalg.norm(v2)
        if norm1 == 0 or norm2 == 0:
            return 0.0
        return float(np.dot(v1, v2) / (norm1 * norm2))

    def get_corpus_similarity(self, text: str) -> list[tuple[str, float]]:
        """Compara um texto com todos os documentos do corpus.

        Args:
            text: Texto para comparar.

        Returns:
            Lista de (id, similaridade) ordenada por similaridade decrescente.
        """
        if not self._fitted or self._corpus_vectors is None or not self._corpus_ids:
            return []

        query_vec = self.embed(text)
        scores = []
        for i, doc_id in enumerate(self._corpus_ids):
            score = self.similarity(query_vec, self._corpus_vectors[i])
            scores.append((doc_id, score))

        scores.sort(key=lambda x: x[1], reverse=True)
        return scores

    @property
    def is_fitted(self) -> bool:
        return self._fitted
