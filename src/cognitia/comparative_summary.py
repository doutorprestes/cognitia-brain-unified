"""Comparative summary generation for Cognitia Brain."""

from __future__ import annotations

import logging
from typing import Dict, List, Optional

from cognitia_brain.db import VectorDB
from cognitia_brain.llm_client import LLMClient

logger = logging.getLogger(__name__)


class ComparativeSummary:
    """Generate comparative summaries across multiple documents."""

    def __init__(self, db: VectorDB, llm: LLMClient):
        self.db = db
        self.llm = llm

    def get_documents_by_theme(self, theme: str, n_results: int = 5) -> List[Dict]:
        """Find documents related to a theme."""
        results = self.db.search(theme, n_results=n_results)

        if not results or not results["documents"] or not results["documents"][0]:
            return []

        documents = []
        for i, doc in enumerate(results["documents"][0]):
            metadata = results["metadatas"][0][i] if results["metadatas"] else {}
            documents.append({
                "content": doc,
                "metadata": metadata,
                "distance": results["distances"][0][i] if results["distances"] else 0
            })

        return documents

    def generate_comparative_summary(
        self,
        theme: str,
        n_documents: int = 5,
        language: str = "pt-BR"
    ) -> Optional[str]:
        """Generate a comparative summary across documents."""
        # Get relevant documents
        documents = self.get_documents_by_theme(theme, n_documents)

        if not documents:
            return None

        # Build context for comparison
        context_parts = []
        for i, doc in enumerate(documents):
            source = doc["metadata"].get("source", f"Documento {i+1}")
            context_parts.append(f"--- Documento {i+1} ({source}) ---\n{doc['content'][:1000]}...")

        context = "\n\n".join(context_parts)

        # Generate comparative summary
        prompt = f"""Você é um assistente de pesquisa acadêmica especializado em análise comparativa.

Analise os documentos abaixo sobre o tema "{theme}" e gere um resumo comparativo em {language} que inclua:

1. **Visão Geral**: Uma síntese geral do tema baseada nos documentos
2. **Pontos de Convergência**: Ideias, métodos ou conclusões que aparecem em múltiplos documentos
3. **Pontos de Divergência**: Diferenças de abordagem, conclusão ou metodologia entre os documentos
4. ** Lacunas Identificadas**: Aspectos do tema que não são cobertos pelos documentos analisados
5. **Sugestões de Pesquisa**: Direções futuras de pesquisa baseadas na análise comparativa

Documentos para análise:

{context}

Resumo Comparativo:"""

        try:
            summary = self.ollama.generate(prompt)
            return summary
        except Exception as e:
            logger.error(f"Error generating comparative summary: {e}")
            return None

    def generate_theme_overview(self, theme: str, n_documents: int = 10) -> Optional[str]:
        """Generate a thematic overview of documents."""
        documents = self.get_documents_by_theme(theme, n_documents)

        if not documents:
            return None

        # Build context
        context_parts = []
        for i, doc in enumerate(documents):
            source = doc["metadata"].get("source", f"Documento {i+1}")
            context_parts.append(f"Documento {i+1} ({source}): {doc['content'][:500]}...")

        context = "\n\n".join(context_parts)

        prompt = f"""Você é um assistente de pesquisa acadêmica.

Analise os documentos sobre "{theme}" e gere um panorama temático em português que inclua:

1. **Definição do Tema**: O que é "{theme}" segundo os documentos
2. **Principais Conceitos**: Termos e conceitos-chave relacionados
3. **Estado da Arte**: O que os documentos dizem sobre o estado atual do tema
4. **Aplicações Práticas**: Exemplos de aplicações mencionados nos documentos
5. **Tendências**: Direções emergentes mencionadas nos documentos

Documentos:

{context}

Panorama Temático:"""

        try:
            overview = self.ollama.generate(prompt)
            return overview
        except Exception as e:
            logger.error(f"Error generating theme overview: {e}")
            return None

    def find_similar_documents(self, document_id: str, n_results: int = 5) -> List[Dict]:
        """Find documents similar to a given document."""
        # Get the document content
        results = self.db.get_by_id(document_id)

        if not results or not results["documents"]:
            return []

        document_content = results["documents"][0]

        # Search for similar documents
        similar = self.db.search(document_content, n_results=n_results + 1)

        if not similar or not similar["documents"] or not similar["documents"][0]:
            return []

        # Filter out the original document
        similar_docs = []
        for i, doc in enumerate(similar["documents"][0]):
            doc_id = similar["ids"][0][i] if similar["ids"] else f"doc_{i}"
            if doc_id != document_id:
                metadata = similar["metadatas"][0][i] if similar["metadatas"] else {}
                similar_docs.append({
                    "id": doc_id,
                    "content": doc,
                    "metadata": metadata,
                    "distance": similar["distances"][0][i] if similar["distances"] else 0
                })

        return similar_docs[:n_results]


# Global comparative summary instance
comparative_summary = None


def get_comparative_summary(db: VectorDB, ollama: OllamaClient) -> ComparativeSummary:
    """Get or create comparative summary instance."""
    global comparative_summary
    if comparative_summary is None:
        comparative_summary = ComparativeSummary(db, ollama)
    return comparative_summary
