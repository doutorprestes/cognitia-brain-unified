# Issue #5 — Bot Telegram Unificado

**Labels:** `fase-4`, `telegram`, `bot`
**Estimate:** 1h

## Descrição

Implementar bot Telegram unificado com comandos básicos e notificação de editais/artigos.

## Tarefas

- [ ] Criar `src/cognitia/bot.py` com classe `CognitiaBot`
- [ ] Implementar handler `/start` (mensagem de boas-vindas + instruções)
- [ ] Implementar handler `/status` (stats: itens coletados, notificados, pendentes)
- [ ] Implementar handler `/pause` e `/resume` (pausa/retoma notificações)
- [ ] Implementar handler `/help` (lista de comandos)
- [ ] Criar função `notificar_item(item)` → envia mensagem formatada
- [ ] Formato da mensagem: título, fonte, link, snippet, tipo (grant/artigo)

## Formato da Notificação

```
📢 NOVO [EDITAL/ARTIGO]

📌 Título: ...
🏛️ Fonte: CAPES
🔗 Link: https://...
📝 Snippet: ...

[👍 Útil] [👎 Não útil]
```

## Comandos

| Comando | Ação |
|---------|------|
| `/start` | Mensagem de boas-vindas |
| `/status` | Estatísticas do sistema |
| `/pause` | Pausa notificações |
| `/resume` | Retoma notificações |
| `/help` | Lista comandos |

## Critérios de Aceite

- [ ] Bot responde a `/start` com mensagem formatada
- [ ] `/status` retorna: total itens, notificados, pendentes, com feedback
- [ ] `/pause` e `/resume` alteram estado (persistir em SQLite)
- [ ] `notificar_item()` envia mensagem sem erros
- [ ] Bot roda em polling (para dev) sem crashes

## Output Esperado

```python
bot = CognitiaBot(token="...", chat_id="...")
bot.iniciar()  # Inicia polling
bot.notificar_item({"title": "...", "url": "...", "source": "CAPES", "type": "grant"})
```
