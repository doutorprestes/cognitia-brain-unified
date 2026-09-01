# Issue #7 — Retreinamento Incremental

**Labels:** `fase-3`, `ml`, `training`
**Estimate:** 45 min

## Descrição

Implementar retreinamento incremental do classificador a cada N novos feedbacks, sem precisar reprocessar todo o histórico.

## Tarefas

- [ ] Criar função `retreinar_incremental(novos_dados, modelo_atual)`
- [ ] Implementar `verificar_necessidade_retreinamento()` → True se >= 20 novos labels
- [ ] Implementar versionamento de modelos (`models/v1.pkl`, `models/v2.pkl`, etc.)
- [ ] Criar função `carregar_modelo_mais_recente()`
- [ ] Implementar `rollback_modelo(versão)` → volta para versão anterior
- [ ] Salvar métricas após cada retreinamento na tabela `model_metrics`
- [ ] Criar `tests/test_retraining.py`

## Critérios de Aceite

- [ ] Retreinamento dispara automaticamente após 20 novos labels
- [ ] Modelo é salvo com versão incrementada
- [ ] Métricas são registradas no SQLite após treino
- [ ] `rollback_modelo()` funciona corretamente
- [ ] Testes passam: `pytest tests/test_retraining.py -v`

## Output Esperado

```python
# Após 20 feedbacks, retreinamento automático
retreinar_se_necessario()
# Log: "Modelo v3 treinado com 45 amostras"
# Métricas salvas: accuracy=0.89, precision=0.91, recall=0.85
```
