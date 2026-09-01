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

## Fluxo do Pipeline

```python
class CognitiaPipeline:
    def executar(self):
        # 1. Scrape
        itens = self.scraper.coletar_todos()
        
        # 2. Dedup
        novos = [e for e in itens if not db.existe_item(e["hash"])]
        
        # 3. Classify
        for item in novos:
            label, conf = self.classifier.prever(item["title"])
            item["confidence"] = conf
            item["label"] = label
        
        # 4. Notify (seleção baseada em confiança)
        notificados = 0
        for item in novos:
            deve, conf = deve_notificar(item["confidence"])
            if deve:
                self.bot.notificar_item(item)
                db.marcar_como_notificado(item["hash"])
                notificados += 1
        
        # 5. Log
        logger.info(f"Pipeline: {len(novos)} novos, {notificados} notificados")
```

## Hermes Cronjob Config

```yaml
schedule: "every 6h"
prompt: "Execute o pipeline CognitiaBrain: scrape → dedup → classify → notify"
skills: ["cognitia-brain"]
```

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
