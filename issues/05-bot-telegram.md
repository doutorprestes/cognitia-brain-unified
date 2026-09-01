# Issue #5 — Bot Telegram Unificado

**Labels:** `fase-5`, `telegram`, `bot`
**Estimate:** 2h

## Descrição

Criar bot Telegram unificado migrando e expandindo a funcionalidade do CognitiaBrain original.

## Tarefas

- [ ] Criar `src/bot/bot.py` com classe `CognitiaBot`
- [ ] Migrar funcionalidades do CognitiaBrain: /start, /status, /pause, /resume, /help
- [ ] Adicionar comando /metrics (mostra precision, recall, F1)
- [ ] Adicionar comando /foco (inferir/add/remove foco de pesquisa)
- [ ] Adicionar comando /sintese (gerar síntese por tema)
- [ ] Botões inline para feedback (👍/👎) em todas as notificações
- [ ] Conversation memory para diálogos contextuais
- [ ] Notificações formatadas com confiança do classificador
- [ ] Criar `tests/test_bot.py`

## Comandos

| Comando | Ação |
|---------|------|
| `/start` | Mensagem de boas-vindas + instruções |
| `/status` | Estatísticas: coletados, notificados, pendentes |
| `/pause` | Pausa notificações |
| `/resume` | Retoma notificações |
| `/metrics` | Precision, recall, F1 atuais |
| `/foco` | Ver/gerenciar foco de pesquisa |
| `/sintese <tema>` | Gerar síntese de escrita |
| `/help` | Lista comandos |

## Formato da Notificação

```
📢 NOVO [EDITAL/ARTIGO]

📌 Título: ...
🏛️ Fonte: CAPES
🔗 Link: https://...
📝 Snippet: ...
🎯 Confiança: 87%

[👍 Útil] [👎 Não útil]
```

## Critérios de Aceite

- [ ] Bot responde a todos os comandos
- [ ] Feedback inline salva no SQLite
- [ ] Notificações incluem confiança do classificador
- [ ] Conversation memory funciona para diálogos
- [ ] Testes passam: `pytest tests/test_bot.py -v`

## Output Esperado

```python
bot = CognitiaBot(token=config.TELEGRAM_BOT_TOKEN, chat_id=config.TELEGRAM_CHAT_ID)
await bot.iniciar()
await bot.notificar_item({"title": "...", "url": "...", "source": "CAPES", "type": "grant", "confidence": 0.87})
```
