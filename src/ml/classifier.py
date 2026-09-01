"""Relevance classifier."""
import logging
from pathlib import Path
from typing import Optional

import joblib
import numpy as np
from sentence_transformers import SentenceTransformer
from sklearn.linear_model import LogisticRegression
from sklearn.exceptions import NotFittedError

from ..shared.config import MODEL_PATH

logger = logging.getLogger(__name__)

EMBEDDING_MODEL = 'paraphrase-multilingual-MiniLM-L12-v2'

class RelevanceClassifier:
    def __init__(self, model_path: Optional[Path] = None):
        self.model_path = Path(model_path or MODEL_PATH)
        self.encoder: Optional[SentenceTransformer] = None
        self.classifier: Optional[LogisticRegression] = None
        self._is_trained = False
        if self.model_path.exists():
            self.load_model(self.model_path)
        else:
            self._create_new_model()

    def _create_new_model(self):
        self.encoder = SentenceTransformer(EMBEDDING_MODEL, device='cpu')
        self.classifier = LogisticRegression(max_iter=1000, random_state=42)
        self._is_trained = False

    def train(self, texts: list, labels: list):
        if self.encoder is None:
            self._create_new_model()
        embeddings = self.encoder.encode(texts, show_progress_bar=True, device='cpu', batch_size=32)
        self.classifier.fit(embeddings, labels)
        self._is_trained = True

    def predict(self, text: str) -> tuple:
        if not self._is_trained:
            raise NotFittedError('Model not trained')
        embedding = self.encoder.encode([text], device='cpu')
        label = self.classifier.predict(embedding)[0]
        confidence = self.get_confidence(text)
        return (int(label), float(confidence))

    def get_confidence(self, text: str) -> float:
        if not self._is_trained:
            raise NotFittedError('Model not trained')
        embedding = self.encoder.encode([text], device='cpu')
        probabilities = self.classifier.predict_proba(embedding)[0]
        classes = list(self.classifier.classes_)
        positive_idx = classes.index(1) if 1 in classes else -1
        return float(probabilities[positive_idx])

    def save_model(self, path: Optional[Path] = None):
        save_path = Path(path or self.model_path)
        save_path.parent.mkdir(parents=True, exist_ok=True)
        joblib.dump({'encoder': self.encoder, 'classifier': self.classifier, 'is_trained': self._is_trained}, save_path)

    def load_model(self, path: Path):
        data = joblib.load(path)
        self.encoder = data['encoder']
        self.classifier = data['classifier']
        self._is_trained = data.get('is_trained', True)
