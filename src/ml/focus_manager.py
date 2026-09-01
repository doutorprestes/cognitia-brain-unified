"""Focus Manager - inferencia de foco de pesquisa."""
import json
import logging
from pathlib import Path
from typing import Optional

from ..shared.config import config

logger = logging.getLogger(__name__)

class FocusManager:
    """Gerencia o foco de pesquisa do usuario."""
    
    def __init__(self, focus_file: Optional[Path] = None):
        self.focus_file = Path(focus_file or config.PROJECT_ROOT / '.chromadb' / 'foco.json')
        self.focus_file.parent.mkdir(parents=True, exist_ok=True)
        self._foco = self._load()
    
    def _load(self) -> list:
        if self.focus_file.exists():
            try:
                return json.loads(self.focus_file.read_text())
            except Exception:
                return []
        return []
    
    def _save(self):
        self.focus_file.write_text(json.dumps(self._foco, ensure_ascii=False, indent=2))
    
    def get_foco(self) -> list:
        return self._foco
    
    def add(self, termo: str):
        termo = termo.strip().lower()
        if termo not in self._foco:
            self._foco.append(termo)
            self._save()
    
    def remove(self, termo: str):
        termo = termo.strip().lower()
        if termo in self._foco:
            self._foco.remove(termo)
            self._save()
    
    def inferir(self, historico: list) -> list:
        """Infere foco a partir do historico de ingestao."""
        if not historico:
            return self._foco
        
        # Conta termos mais frequentes
        termos = {}
        for item in historico:
            title = item.get('title', '').lower()
            for palavra in title.split():
                if len(palavra) > 4:
                    termos[palavra] = termos.get(palavra, 0) + 1
        
        # Top 10 termos
        top = sorted(termos.items(), key=lambda x: x[1], reverse=True)[:10]
        return [t[0] for t in top]
