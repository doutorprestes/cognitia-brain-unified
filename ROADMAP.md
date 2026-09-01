# CognitiaBrain Unified — Roadmap

> Sistema unificado de monitoramento acadêmico: grants + artigos + IA.

## Visão Geral

**Problema:** Editais de fomento e artigos científicos são monitorados em sistemas separados (CognitiaBrain, GrantWatch, IA-Brasil, InvestIA, etc.), com bots Telegram diferentes, sem compartilhamento de inteligência ou aprendizado cruzado.

**Objetivo:** Pipeline unificado que coleta, classifica e notifica sobre grants E artigos, aprendendo com feedback do usuário para melhorar relevância ao longo do tempo.

**Princípios:**
- Código mínimo que resolve o problema
- Sem funcionalidades extras não solicitadas
- Manter estilo e convenções existentes
- Projetos originais inalterados (rollback seguro)

---

## Fases

### Fase 1 — Fundação (Semana 1-2)
- [ ] Estrutura de diretórios e configuração base
- [ ] Módulo de configuração unificado (YAML + .env)
- [ ] Banco de dados SQLite com schema unificado
- [ ] Sistema de deduplicação (hash SHA-256)
- [ ] Logger e tratamento de erros centralizados

### Fase 2 — Scrapers Unificados (Semana 2-3)
- [ ] Migrar scrapers GrantWatch (FINEP, CNPq, CAPES, FAPESP, etc.)
- [ ] Migrar scrapers CognitiaBrain (artigos, PDFs, URLs)
- [ ] Padronizar interface de scraper (classe base abstrata)
- [ ] Sistema de agendamento unificado (APScheduler)
- [ ] Retry com backoff e tratamento de erros

### Fase 3 — Classificação ML (Semana 3-4)
- [ ] Classificador de relevância (SetFit + MiniLM)
- [ ] Embeddings unificados (ChromaDB)
- [ ] Confidence gate (conservador/moderado/agressivo)
- [ ] Retreinamento incremental (a cada 20 feedbacks)
- [ ] Avaliação de métricas (precision, recall, F1)

### Fase 4 — Bot Telegram Unificado (Semana 4-5)
- [ ] Bot único para grants + artigos
- [ ] Comandos: /start, /status, /pause, /resume, /help
- [ ] Botões inline para feedback (👍/👎)
- [ ] Notificações formatadas com confiança
- [ ] Conversation memory para diálogos contextuais

### Fase 5 — Dashboard Web (Semana 5-6)
- [ ] FastAPI + Jinja2 + HTMX
- [ ] Visualização de grants + artigos
- [ ] Filtros por fonte, data, relevância
- [ ] Métricas de performance
- [ ] Gestão de foco de pesquisa

### Fase 6 — Inteligência Ativa (Semana 6-7)
- [ ] FocusManager (inferência de foco)
- [ ] Detecção de conexões (cosseno + grafo)
- [ ] Síntese de escrita por tema
- [ ] Scout web automatizado
- [ ] Weekly digest

### Fase 7 — Integração e Polish (Semana 7-8)
- [ ] Testes unitários e e2e
- [ ] Documentação completa
- [ ] CI/CD (GitHub Actions)
- [ ] Deploy automatizado
- [ ] Migração de dados históricos

---

## Arquitetura

```
cognitia-brain-unified/
├── src/
│   ├── cognitia/          # Artigos (migrado do cognitia-brain)
│   │   ├── bot.py         # Telegram bot
│   │   ├── pipeline.py    # Pipeline de ingestão
│   │   ├── llm_client.py  # LLM (OpenRouter/Ollama)
│   │   ├── graph.py       # Knowledge graph
│   │   └── ...
│   ├── grants/            # Editais (migrado do grantwatch)
│   │   ├── finep.ts
│   │   ├── cnpq.ts
│   │   ├── capes.ts
│   │   └── ...
│   ├── shared/            # Código compartilhado
│   │   ├── config.py
│   │   ├── database.py
│   │   ├── logger.py
│   │   └── ...
│   ├── web/               # Dashboard web
│   │   ├── main.py
│   │   └── templates/
│   └── scripts/           # Scripts utilitários
├── tests/
├── docs/
├── issues/
├── data/
└── models/
```

---

## Stack Técnica

| Componente | Ferramenta | Justificativa |
|------------|------------|---------------|
| **Linguagem** | Python 3.11+ | NLP/ML nativo, ChromaDB, scrapers |
| **Bot** | python-telegram-bot v21 | Async, estável, Bot API 7.0+ |
| **Vector DB** | ChromaDB | Embeddings, busca semântica |
| **Embeddings** | paraphrase-multilingual-MiniLM-L12-v2 | Multilíngue, CPU-friendly |
| **Classificador** | SetFit + LogisticRegression | Few-shot, incremental |
| **Scrapers** | Playwright + BeautifulSoup | JS-rendered pages |
| **LLM** | OpenRouter → Ollama Cloud | Cloud-first, fallback local |
| **Web** | FastAPI + Jinja2 + HTMX | Leve, server-side |
| **Agendamento** | APScheduler | Cron, intervalos |
| **Storage** | SQLite | Zero config, portável |

---

## Métricas de Sucesso

| Métrica | Meta |
|---------|------|
| Cobertura de fontes | 9+ scrapers funcionando |
| Deduplicação | 0% de notificações duplicadas |
| Precisão (relevância) | > 85% de notificações úteis |
| Latência (scrape → notify) | < 5 minutos |
| Feedback loop | Retreinamento a cada 20 labels |

---

## Riscos e Mitigações

| Risco | Mitigação |
|-------|-----------|
| Mudança de layout nas fontes | Múltiplos seletores + fallback |
| Drift do modelo | Retreinamento periódico |
| Rate limit Telegram | Batching + retry com backoff |
| Dados de feedback enviesados | Diversity sampling |
| Conflito de porta web | Porta canônica 8081 |

---

## Projetos Originais (Inalterados)

- [CognitiaBrain](https://github.com/doutorprestes/cognitia-brain) — monitor de artigos
- [GrantWatch](https://github.com/doutorprestes/grantwatch) — monitor de editais
- [IA-Brasil](https://github.com/doutorprestes/ia-brasil) — dados públicos brasileiros
- [InvestIA](https://github.com/doutorprestes/investia) — dados de investimento
- [buscador_de_grants](https://github.com/doutorprestes/buscador-de-grants) — buscador .NET
- [grantwatch_evolution](https://github.com/doutorprestes/grantwatch-evolution) — dashboard Next.js
- [inteligencia-ai](https://github.com/doutorprestes/inteligencia-ai) — scrapers + webapp

---

## Referências

- [Scrapy](https://scrapy.org/) — framework de scraping
- [ChromaDB](https://trychroma.com/) — vector database
- [SetFit](https://github.com/huggingface/setfit) — few-shot classification
- [python-telegram-bot](https://python-telegram-bot.org/) — bot framework
