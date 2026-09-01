"""Metrics module."""
import logging
from typing import Optional

from sklearn.metrics import precision_score, recall_score, f1_score

from .database import UnifiedDatabase

logger = logging.getLogger(__name__)

class GrantWatchMetrics:
    def __init__(self, db: UnifiedDatabase):
        self.db = db

    def calcular(self, y_true: list, y_pred: list) -> dict:
        if not y_true or not y_pred:
            return {'precision': 0.0, 'recall': 0.0, 'f1': 0.0}
        return {
            'precision': round(precision_score(y_true, y_pred, zero_division=0), 4),
            'recall': round(recall_score(y_true, y_pred, zero_division=0), 4),
            'f1': round(f1_score(y_true, y_pred, zero_division=0), 4),
        }

    def gerar_relatorio(self) -> dict:
        return {
            'total_items': self.db.count_items(),
            'total_notificados': self.db.count_notificados(),
            'total_feedback': self.db.count_labels(),
            'precision': 0.0, 'recall': 0.0, 'f1': 0.0,
        }

    def formatar_relatorio(self) -> str:
        r = self.gerar_relatorio()
        return (
            f'📊 MÉTRICAS COGNITIABRAIN\n\n'
            f'📈 Volume:\n'
            f'• Itens coletados: {r["total_items"]}\n'
            f'• Notificados: {r["total_notificados"]}\n'
            f'• Com feedback: {r["total_feedback"]}\n'
        )

def deve_notificar(confidence: float, mode: str = 'moderado') -> tuple:
    limiares = {'conservador': 0.8, 'moderado': 0.6, 'agressivo': 0.5}
    limiar = limiares.get(mode, 0.6)
    if confidence > limiar:
        return (True, confidence)
    elif confidence < 0.4:
        return (False, confidence)
    else:
        return (None, confidence)
