"""Gerenciador do Banco de Dados Vetorial Local (ChromaDB)."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional

import chromadb
from chromadb.utils import embedding_functions

from cognitia_brain.config import Config


class VectorDB:
    def __init__(self, config: Config, db_name: str = "cognitia_vectors") -> None:
        self.config = config
        self.db_path = config.acervo_dir.parent / ".chromadb"
        self.db_path.mkdir(parents=True, exist_ok=True)
        
        self.client = chromadb.PersistentClient(path=str(self.db_path))
        
        # Usar o modelo local da SentenceTransformers
        self.emb_fn = embedding_functions.SentenceTransformerEmbeddingFunction(
            model_name="paraphrase-multilingual-MiniLM-L12-v2"
        )
        
        self.collection = self.client.get_or_create_collection(
            name=db_name,
            embedding_function=self.emb_fn
        )

    def add_document(self, doc_id: str, texts: List[str], metadatas: List[Dict[str, Any]]) -> None:
        """Adiciona múltiplos chunks de um documento à collection."""
        if not texts:
            return
            
        ids = [f"{doc_id}_chunk_{i}" for i in range(len(texts))]
        
        self.collection.add(
            documents=texts,
            metadatas=metadatas,
            ids=ids
        )

    def add_summary(self, doc_id: str, summary: str, metadata: Dict[str, Any]) -> None:
        """Adiciona o resumo executivo gerado pelo LLM."""
        meta = metadata.copy()
        meta["is_summary"] = True
        
        self.collection.add(
            documents=[summary],
            metadatas=[meta],
            ids=[f"{doc_id}_summary"]
        )

    def search(self, query: str, n_results: int = 5, where: Optional[Dict[str, Any]] = None) -> dict:
        """Realiza busca semântica no banco."""
        results = self.collection.query(
            query_texts=[query],
            n_results=n_results,
            where=where
        )
        return results

    def count(self) -> int:
        """Retorna o número de vetores na collection."""
        return self.collection.count()
