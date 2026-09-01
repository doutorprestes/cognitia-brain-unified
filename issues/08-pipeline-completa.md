# Issue #8 — Pipeline Autônoma

**Labels:** `fase-5`, `automação`, `cronjob`
**Estimate:** 1h

## Descrição

Implementar pipeline completa e autônoma: scrape → dedup → classify → notify, rodando via Hermes cronjob.

## Tarefas

- [ ] Criar `src/shared/pipeline.py` com classe `CognitiaPipeline`
- [ ] Implementar `executar()` → roda pipeline completa
- [ ] Integrar com scrapers existentes
- [ ] Adicionar logs estruturados (início, fim, erros, stats)
- [ ] Implementar retry com backoff para falhas de rede
- [ ] Criar configuração de schedule no Hermes (6h em 6h)
- [ ] Adicionar handler `/run` no bot (executa pipeline manualmente)
- [ ] Criar `tests/test_pipeline.py`

## Critérios de Aceite

- [ ] `executar()` roda sem erros
- [ ] Itens duplicados não são re-notificados
- [ ] Apenas itens com confiança > limiar são notificados
- [ ] Logs mostram: total coletados, novos, notificados, erros
- [ ] `/run` no bot executa pipeline manualmente
- [ ] Testes passam: `pytest tests/test_pipeline.py -v`

## Output Esperado

```python
pipeline = CognitiaPipeline()
pipeline.executar()
# Log: "Pipeline: 15 coletados, 3 novos, 2 notificados"
```
