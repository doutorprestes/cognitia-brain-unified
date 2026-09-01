# Issue #9 — Dashboard Web

**Labels:** `fase-5`, `web`, `dashboard`
**Estimate:** 2h

## Descrição

Implementar dashboard web para visualização de grants + artigos e métricas do sistema.

## Tarefas

- [ ] Criar `src/web/main.py` com FastAPI
- [ ] Implementar rota `/` (lista grants + artigos)
- [ ] Implementar rota `/status` (métricas do sistema)
- [ ] Implementar rota `/sintese` (gerar síntese por tema)
- [ ] Criar templates Jinja2 com HTMX
- [ ] Adicionar filtros por fonte, data, relevância
- [ ] Criar `tests/test_web.py`

## Rotas

| Rota | Descrição |
|------|-----------|
| `/` | Lista grants + artigos |
| `/status` | Métricas do sistema |
| `/sintese` | Gerar síntese por tema |
| `/sintese/{slug}` | Visualizar síntese |
| `/api/foco` | Gestão de foco |
| `/api/metrics` | Métricas JSON |

## Critérios de Aceite

- [ ] Dashboard carrega sem erros
- [ ] Filtros funcionam (fonte, data, relevância)
- [ ] Métricas são exibidas corretamente
- [ ] Testes passam: `pytest tests/test_web.py -v`

## Output Esperado

```bash
uvicorn src.web.main:app --port 8081
# Dashboard disponível em http://localhost:8081
```
