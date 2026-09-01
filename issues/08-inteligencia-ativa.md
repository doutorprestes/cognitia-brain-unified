# Issue #8 — Inteligência Ativa

**Labels:** `fase-7`, `ml`, `ia`, `inteligencia`
**Estimate:** 2h

## Descrição

Implementar inteligência ativa: FocusManager, detecção de conexões, síntese de escrita e scout web.

## Tarefas

- [ ] Criar `src/ml/focus_manager.py` (inferência de foco)
- [ ] Criar `src/ml/connections.py` (detecção de conexões via cosseno + grafo)
- [ ] Criar `src/ml/synthesis.py` (síntese de escrita por tema)
- [ ] Criar `src/ml/scout.py` (scout web automatizado)
- [ ] Criar `src/ml/scheduler.py` (weekly digest, análise diária)
- [ ] Integrar com bot Telegram (`/foco`, `/sintese`)
- [ ] Criar `tests/test_inteligencia.py`

## Funcionalidades

### FocusManager
- Inferir foco a partir do histórico de ingestão
- Adicionar/remover foco manualmente
- Persistir estado em `.chromadb/foco.json`

### Connections
- Detectar conexões entre documento novo e fichamentos existentes
- Similaridade cosseno + entidades do grafo
- Outbox de alertas (`.chromadb/alertas.json`)

### Synthesis
- Gerar síntese de escrita por tema
- Salvar em `rascunhos/<slug>.md`

### Scout
- Buscar web por palavras-chave do foco
- Feeds RSS, arXiv, etc.

## Critérios de Aceite

- [ ] FocusManager infere foco corretamente
- [ ] Conexões são detectadas com similaridade > 0.7
- [ ] Síntese gera rascunhos coerentes
- [ ] Scout retorna resultados relevantes
- [ ] Testes passam: `pytest tests/test_inteligencia.py -v`

## Output Esperado

```python
fm = FocusManager()
fm.inferir_foco()
# ["IA", "ML", "NLP"]

conns = detectar_conexoes(novo_documento)
# [{"doc": "...", "similarity": 0.85, "entidades": ["IA", "ML"]}]
```
