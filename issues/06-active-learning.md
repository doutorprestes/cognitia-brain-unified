# Issue #6 — Active Learning Loop

**Labels:** `fase-5`, `ml`, `feedback`, `active-learning`
**Estimate:** 1h

## Descrição

Implementar coleta de feedback via botões inline no Telegram (👍/👎) para alimentar o classificador e retreinar o modelo incrementalmente.

## Tarefas

- [ ] Criar handler de callback para botões 👍/👎
- [ ] Implementar `processar_feedback(item_hash, label)` → salva no SQLite
- [ ] Atualizar mensagem original com confirmação ("✅ Obrigado pelo feedback!")
- [ ] Implementar `verificar_necessidade_retreinamento()` → True se >= 20 novos labels
- [ ] Implementar retreinamento incremental automático
- [ ] Criar função `calcular_metricas() → dict` (precision, recall, F1)
- [ ] Adicionar comando `/metrics` no bot (mostra métricas atuais)
- [ ] Criar `tests/test_feedback.py`

## Fluxo

```
1. Bot notifica item com botões [👍 Útil] [👎 Não útil]
2. Usuário clica em um dos botões
3. Callback salva feedback no SQLite
4. Mensagem é editada com confirmação
5. A cada 20 feedbacks, modelo é retreinado automaticamente
```

## Callback Data Format

```python
# Formato: "feedback:{hash}:{label}"
callback_data = f"feedback:{item_hash}:{1}"  # 👍 Útil
callback_data = f"feedback:{item_hash}:{0}"  # 👎 Não útil
```

## Critérios de Aceite

- [ ] Botões aparecem em todas as notificações
- [ ] Clicar em 👍 salva label=1 no SQLite
- [ ] Clicar em 👎 salva label=0 no SQLite
- [ ] Mensagem é editada com confirmação
- [ ] Retreinamento automático após 20 feedbacks
- [ ] `/metrics` retorna precision, recall, F1 atuais
- [ ] Testes passam: `pytest tests/test_feedback.py -v`

## Output Esperado

```python
# Callback handler
async def feedback_callback(update: Update, context):
    query = update.callback_query
    _, hash, label = query.data.split(":")
    db.salvar_feedback(hash, int(label), confidence=0.0)
    await query.edit_message_text("✅ Obrigado pelo feedback!")
    retreinar_se_necessario()
```
