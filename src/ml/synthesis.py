"""Synthesis - sintese de escrita por tema."""
import logging
from pathlib import Path
from typing import Optional

from ..shared.config import config

logger = logging.getLogger(__name__)

class SynthesisGenerator:
    """Gera sintese de escrita por tema."""
    
    def __init__(self, output_dir: Optional[Path] = None):
        self.output_dir = Path(output_dir or config.PROJECT_ROOT / 'rascunhos')
        self.output_dir.mkdir(parents=True, exist_ok=True)
    
    def gerar(self, tema: str, documentos: list) -> str:
        """Gera sintese de escrita para um tema."""
        slug = tema.lower().replace(' ', '_')
        output_file = self.output_dir / f'{slug}.md'
        
        conteudo = f'# Sintese: {tema}\n\n'
        conteudo += f'## Documentos analisados\n\n'
        
        for i, doc in enumerate(documentos, 1):
            conteudo += f'{i}. **{doc.get("title", "Sem titulo")}**\n'
            conteudo += f'   - Fonte: {doc.get("source", "Desconhecida")}\n'
            conteudo += f'   - URL: {doc.get("url", "N/A")}\n\n'
        
        conteudo += f'## Pontos principais\n\n'
        conteudo += f'- [ ] Analisar cada documento\n'
        conteudo += f'- [ ] Identificar padroes\n'
        conteudo += f'- [ ] Sintetizar conclusoes\n'
        
        output_file.write_text(conteudo, encoding='utf-8')
        return str(output_file)
    
    def listar(self) -> list:
        """Lista todas as sinteses geradas."""
        return [f.stem for f in self.output_dir.glob('*.md')]
