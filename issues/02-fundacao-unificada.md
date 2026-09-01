# Issue #2 — Fundação Unificada

**Labels:** `fase-2`, `infraestrutura`, `fundacao`
**Estimate:** 1h

## Descrição

Criar módulos compartilhados que serão usados por todo o sistema unificado: config, database, logger.

## Tarefas

- [ ] Criar `src/shared/config.py` (carrega .env, constantes centralizadas)
- [ ] Criar `src/shared/database.py` (SQLite com schema unificado para grants + artigos)
- [ ] Criar `src/shared/logger.py` (logging estruturado)
- [ ] Criar `src/shared/events.py` (sistema de eventos assíncrono)
- [ ] Definir schema unificado para items (grants + artigos)
- [ ] Criar `requirements.txt` consolidado
- [ ] Criar `.env.example` com todas as variáveis necessárias

## Schema Unificado (items)

```sql
CREATE TABLE IF NOT EXISTS items (
    hash TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    url TEXT NOT NULL,
    source TEXT NOT NULL,
    type TEXT NOT NULL CHECK(type IN ('grant', 'artigo')),
    snippet TEXT,
    confidence REAL DEFAULT 0.0,
    scraped_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    notified_at TIMESTAMP
);

CREATE TABLE IF NOT EXISTS feedback (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    item_hash TEXT NOT NULL,
    label INTEGER NOT NULL CHECK(label IN (0, 1)),
    confidence REAL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (item_hash) REFERENCES items(hash)
);
```

## Critérios de Aceite

- [ ] `from src.shared.config import config` funciona
- [ ] `from src.shared.database import UnifiedDatabase` funciona
- [ ] Insert e dedup funcionam para grants e artigos
- [ ] Logger configurado com níveis (INFO, DEBUG, ERROR)

## Output Esperado

```python
from src.shared.config import config
from src.shared.database import UnifiedDatabase
from src.shared.logger import logger

db = UnifiedDatabase(config.DB_PATH)
db.insert_item({"title": "...", "url": "...", "source": "CAPES", "type": "grant"})
```
