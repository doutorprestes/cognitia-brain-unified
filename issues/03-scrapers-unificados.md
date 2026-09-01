# Issue #3 — Scrapers Unificados

**Labels:** `fase-2`, `scraper`, `grants`
**Estimate:** 2h

## Descrição

Migrar e unificar scrapers do GrantWatch e CognitiaBrain para uma interface comum.

## Tarefas

- [ ] Criar classe base abstrata `BaseScraper` em `src/shared/scraper_base.py`
- [ ] Migrar scrapers GrantWatch: FINEP, CNPq, CAPES, FAPESP, EMBRAPII, etc.
- [ ] Migrar scrapers CognitiaBrain: artigos PDF, URLs, feeds
- [ ] Padronizar output: `{title, url, source, type, snippet}`
- [ ] Implementar retry com backoff (máx 3 tentativas)
- [ ] Adicionar logging estruturado
- [ ] Criar `tests/test_scrapers.py`

## Interface Base

```python
from abc import ABC, abstractmethod

class BaseScraper(ABC):
    @abstractmethod
    def coletar(self) -> list[dict]:
        """Coleta itens da fonte. Retorna lista de dicts com title, url, source, type, snippet."""
        pass
    
    @property
    @abstractmethod
    def nome(self) -> str:
        """Nome da fonte."""
        pass
```

## Critérios de Aceite

- [ ] Cada scraper retorna lista padronizada
- [ ] Retry funciona após falha de rede
- [ ] Log mostra: total coletados, novos, erros
- [ ] Testes passam para cada scraper

## Output Esperado

```python
scraper = FinepScraper()
items = scraper.coletar()
# [{"title": "...", "url": "...", "source": "FINEP", "type": "grant", "snippet": "..."}]
```
