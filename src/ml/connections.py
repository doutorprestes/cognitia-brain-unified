"""Connections - deteccao de conexoes entre documentos."""
import logging
from typing import Optional

from sentence_transformers import SentenceTransformer
from sklearn.metrics.pairwise import cosine_similarity
import numpy as np

from ..shared.config import config

logger = logging.getLogger(__name__)

class ConnectionDetector:
    """Detecta conexoes entre documentos novos e fichamentos existentes."""
    
    def __init__(self, model_name: str = 'paraphrase-multilingual-MiniLM-L12-v2'):
        self.encoder = SentenceTransformer(model_name, device='cpu')
    
    def detectar(self, novo_doc: str, existentes: list, threshold: float = 0.7) -> list:
        """Detecta conexoes entre novo documento e lista de existentes."""
        if not existentes:
            return []
        
        # Gera embeddings
        embedding_novo = self.encoder.encode([novo_doc])
        embeddings_existentes = self.encoder.encode(existentes)
        
        # Calcula similaridade
        similaridades = cosine_similarity(embedding_novo, embeddings_existentes)[0]
        
        conexoes = []
        for idx, sim in enumerate(similaridades):
            if sim >= threshold:
                conexoes.append({
                    'doc': existentes[idx],
                    'similarity': float(sim),
                    'idx': idx
                })
        
        return sorted(conexoes, key=lambda x: x['similarity'], reverse=True)
