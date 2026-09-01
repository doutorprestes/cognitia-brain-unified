"""Hybrid search combining semantic and keyword search for Cognitia Brain."""

from __future__ import annotations

import logging
import re
from collections import Counter
from typing import Any, Dict, List, Optional, Tuple

from cognitia_brain.db import VectorDB

logger = logging.getLogger(__name__)


class HybridSearch:
    """Combine semantic (vector) search with keyword (BM25-like) search."""

    def __init__(self, db: VectorDB, semantic_weight: float = 0.7, keyword_weight: float = 0.3):
        self.db = db
        self.semantic_weight = semantic_weight
        self.keyword_weight = keyword_weight

    def _tokenize(self, text: str) -> List[str]:
        """Simple tokenization for keyword matching."""
        # Convert to lowercase and split by non-alphanumeric
        text = text.lower()
        tokens = re.findall(r'\b\w+\b', text)
        return tokens

    def _calculate_bm25_score(
        self,
        query_tokens: List[str],
        doc_tokens: List[str],
        avg_doc_length: float,
        k1: float = 1.5,
        b: float = 0.75
    ) -> float:
        """Calculate BM25-like score for a document."""
        doc_length = len(doc_tokens)
        doc_counter = Counter(doc_tokens)

        score = 0.0
        for token in query_tokens:
            if token in doc_counter:
                tf = doc_counter[token]
                # BM25 formula
                numerator = tf * (k1 + 1)
                denominator = tf + k1 * (1 - b + b * doc_length / avg_doc_length)
                score += numerator / denominator

        return score

    def search(
        self,
        query: str,
        n_results: int = 5,
        where: Optional[Dict] = None
    ) -> List[Dict[str, Any]]:
        """Perform hybrid search combining semantic and keyword matching."""
        # Get semantic search results
        semantic_results = self.db.search(query, n_results=n_results * 2, where=where)

        if not semantic_results or not semantic_results["documents"] or not semantic_results["documents"][0]:
            return []

        documents = semantic_results["documents"][0]
        metadatas = semantic_results["metadatas"][0] if semantic_results["metadatas"] else [{}] * len(documents)
        distances = semantic_results["distances"][0] if semantic_results["distances"] else [0] * len(documents)

        # Tokenize query
        query_tokens = self._tokenize(query)

        # Calculate average document length for BM25
        doc_tokens_list = [self._tokenize(doc) for doc in documents]
        avg_doc_length = sum(len(tokens) for tokens in doc_tokens_list) / len(doc_tokens_list) if doc_tokens_list else 1

        # Calculate hybrid scores
        hybrid_results = []
        for i, (doc, metadata, distance) in enumerate(zip(documents, metadatas, distances)):
            # Semantic score (convert distance to similarity)
            semantic_score = 1.0 / (1.0 + distance)

            # Keyword score
            doc_tokens = doc_tokens_list[i]
            keyword_score = self._calculate_bm25_score(query_tokens, doc_tokens, avg_doc_length)

            # Normalize keyword score
            max_keyword_score = len(query_tokens) * (1.5 + 1) / (1.5 * (1 - 0.3 + 0.3 * avg_doc_length / avg_doc_length))
            if max_keyword_score > 0:
                keyword_score = keyword_score / max_keyword_score

            # Hybrid score
            hybrid_score = (
                self.semantic_weight * semantic_score +
                self.keyword_weight * keyword_score
            )

            hybrid_results.append({
                "document": doc,
                "metadata": metadata,
                "score": hybrid_score,
                "semantic_score": semantic_score,
                "keyword_score": keyword_score,
                "distance": distance
            })

        # Sort by hybrid score (descending)
        hybrid_results.sort(key=lambda x: x["score"], reverse=True)

        # Return top N results
        return hybrid_results[:n_results]

    def search_with_reranking(
        self,
        query: str,
        n_results: int = 5,
        where: Optional[Dict] = None
    ) -> List[Dict[str, Any]]:
        """Search with reranking for better relevance."""
        # Get more results than needed
        initial_results = self.search(query, n_results=n_results * 3, where=where)

        if not initial_results:
            return []

        # Simple reranking based on query term coverage
        query_tokens = set(self._tokenize(query))

        for result in initial_results:
            doc_tokens = set(self._tokenize(result["document"]))
            coverage = len(query_tokens.intersection(doc_tokens)) / len(query_tokens) if query_tokens else 0

            # Boost score based on coverage
            result["rerank_score"] = result["score"] * (1 + coverage * 0.5)

        # Sort by reranked score
        initial_results.sort(key=lambda x: x["rerank_score"], reverse=True)

        return initial_results[:n_results]


# Global hybrid search instance
hybrid_search = None


def get_hybrid_search(db: VectorDB) -> HybridSearch:
    """Get or create hybrid search instance."""
    global hybrid_search
    if hybrid_search is None:
        hybrid_search = HybridSearch(db)
    return hybrid_search
