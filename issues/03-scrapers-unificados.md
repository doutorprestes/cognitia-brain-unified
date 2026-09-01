# Issue #3 — Scrapers Unificados

**Labels:** `fase-3`, `scraper`, `grants`, `artigos`
**Estimate:** 3h

## Descrição

Criar classe base abstrata e migrar/consolidar todos os scrapers dos projetos originais para uma interface unificada.

## Tarefas

- [ ] Criar `src/shared/scraper_base.py` com classe `BaseScraper`
- [ ] Consolidar scrapers Python: FINEP, CNPq, CAPES, FAPESP, EMBRAPII, SENAI
- [ ] Consolidar scrapers TypeScript (GrantWatch, inteligencia-ai) — migrar para Python ou criar bridge
- [ ] Integrar coletor IA-Brasil (DOU, CGEE, MCTI, CGU)
- [ ] Integrar ETL InvestIA (Câmara, Senado, DOU)
- [ ] Criar `src/scrapers/grants/` para editais
- [ ] Criar `src/scrapers/artigos/` para artigos (arXiv, SemanticScholar)
- [ ] Criar `src/scrapers/gov/` para dados governamentais
- [ ] Implementar retry com backoff (máx 3 tentativas)
- [ ] Adicionar rate limiting e proxy rotation
- [ ] Criar `tests/test_scrapers.py`

## Interface Base

```python
from abc import ABC, abstractmethod

class BaseScraper(ABC):
    @abstractmethod
    def coletar(self) -> list[dict]:
        """Coleta itens da fonte. Retorna lista de dicts."""
        pass
    
    @property
    @abstractmethod
    def nome(self) -> str:
        """Nome da fonte."""
        pass
    
    @property
    @abstractmethod
    def tipo(self) -> str:
        """Tipo: 'grant' ou 'artigo'."""
        pass
```

## Critérios de Aceite

- [ ] Todos os scrapers implementam `BaseScraper`
- [ ] Output padronizado: `{title, url, source, type, snippet}`
- [ ] Retry funciona após falha de rede
- [ ] Log mostra: total coletados, novos, erros
- [ ] Testes passam para cada scraper

## Output Esperado

```python
from src.scrapers.grants.finep import FinepScraper

scraper = FinepScraper()
items = scraper.coletar()
# [{"title": "...", "url": "...", "source": "FINEP", "type": "grant", "snippet": "..."}]
```
