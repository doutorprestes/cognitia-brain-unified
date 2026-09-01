# Issue #2 — Sistema de Deduplicação (SQLite)

**Labels:** `infraestrutura`, `fase-1`, `database`
**Estimate:** 45 min

## Descrição

Implementar camada de persistência em SQLite para armazenar editais/artigos coletados e evitar notificações duplicadas.

## Tarefas

- [ ] Criar `src/shared/database.py` com classe `UnifiedDatabase`
- [ ] Implementar schema: tabelas `items`, `feedback`, `model_metrics`
- [ ] Implementar `insert_item(item) → bool` (retorna True se inserido, False se duplicado)
- [ ] Implementar `existe_item(hash) -> bool`
- [ ] Implementar `get_itens_nao_notificados() → list`
- [ ] Implementar `marcar_como_notificado(hash)`
- [ ] Implementar `salvar_feedback(hash, label, confidence)`
- [ ] Criar `tests/test_database.py` com testes unitários

## Schema SQL

```sql
CREATE TABLE IF NOT EXISTS items (
    hash TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    url TEXT NOT NULL,
    source TEXT NOT NULL,
    type TEXT NOT NULL,  -- 'grant' ou 'artigo'
    snippet TEXT,
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

CREATE TABLE IF NOT EXISTS model_metrics (
    version INTEGER PRIMARY KEY AUTOINCREMENT,
    accuracy REAL,
    precision REAL,
    recall REAL,
    n_train_samples INTEGER,
    trained_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

## Critérios de Aceite

- [ ] Inserir item duplicado retorna `False`
- [ ] `get_itens_nao_notificados()` retorna apenas itens sem `notified_at`
- [ ] Testes passam: `pytest tests/test_database.py -v`
- [ ] Hash é SHA-256 de `title + url` (normalizado: lowercase, strip)

## Output Esperado

```python
db = UnifiedDatabase("data/cognitia.db")
db.insert_item({"title": "Edital XYZ", "url": "...", "source": "CAPES", "type": "grant"})
# True (primeira vez)
db.insert_item({"title": "Edital XYZ", "url": "...", "source": "CAPES", "type": "grant"})
# False (duplicado)
```
