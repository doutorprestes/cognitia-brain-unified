import yaml
from pathlib import Path
from typing import Optional

CONFIG_PATH = Path(__file__).resolve().parent.parent.parent / 'config' / 'interesses.yaml'

class RelevanciaEngine:
    def __init__(self, config_path=None):
        self.config_path = config_path or CONFIG_PATH
        self._config = None
    
    @property
    def config(self):
        if self._config is None:
            with open(self.config_path) as f:
                self._config = yaml.safe_load(f)
        return self._config
    
    def score(self, item):
        title = (item.get('title', '') or '').lower()
        snippet = (item.get('snippet', '') or '').lower()
        source = (item.get('source', '') or '').lower()
        tipo = (item.get('type', '') or '').lower()
        text = title + ' ' + snippet
        
        palavras_chave = self.config.get('palavras_chave', [])
        score = 0.0
        
        for kw in palavras_chave:
            kw_lower = kw.lower()
            if kw_lower in title:
                score += 0.3
            elif kw_lower in snippet:
                score += 0.1
        
        fontes = self.config.get('fontes_preferidas', [])
        for fonte in fontes:
            if fonte.lower() in source or fonte.lower() in text:
                score += 0.1
        
        if tipo in ['grant', 'artigo']:
            score += 0.05
        
        generic_terms = ['bert:', 'gpt-4 technical report', 'transformer (original)', 
                        'attention is all you need']
        for gt in generic_terms:
            if gt in title:
                score *= 0.1
        
        return min(score, 1.0)
    
    def filtrar(self, items, threshold=0.15):
        scored = [(item, self.score(item)) for item in items]
        filtered = [(item, s) for item, s in scored if s >= threshold]
        filtered.sort(key=lambda x: x[1], reverse=True)
        return [item for item, _ in filtered]

engine = RelevanciaEngine()
