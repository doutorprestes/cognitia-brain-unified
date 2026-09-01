# CognitiaBrain Unified — Roadmap

> Sistema unificado de monitoramento acadêmico: grants + artigos + IA.

## Status: ✅ COMPLETO

**7 projetos importados** (código legado, sem modificações):
- CognitiaBrain (artigos + LLM + Telegram bot)
- GrantWatch (editais + scrapers TS)
- IA-Brasil (coletor dados públicos + 20+ módulos)
- InvestIA (ETL + API + backend)
- buscador_de_grants (.NET + ML.NET)
- grantwatch_evolution (Next.js dashboard)
- inteligencia-ai (scrapers + webapp)

**Total:** ~220 arquivos, ~314k linhas de código, 12 subdiretórios em `src/`.

---

## Fases

### Fase 1 — Inventário e Limpeza ✅
- [x] Mapear todas as fontes de dados e scrapers
- [x] Identificar sobreposições e duplicações
- [x] Remover código morto e dependências não utilizadas
- [x] Padronizar estrutura de diretórios
- [x] Documentar arquitetura atual (como-está)

### Fase 2 — Fundação Unificada ✅
- [x] Módulo de configuração centralizado (`.env` + YAML)
- [x] Banco de dados SQLite unificado (schema padronizado)
- [x] Sistema de deduplicação (hash SHA-256)
- [x] Logger e tratamento de erros centralizados
- [x] Pipeline de eventos assíncrono

### Fase 3 — Scrapers Unificados ✅
- [x] Classe base abstrata `BaseScraper` (interface única)
- [x] Migrar scrapers Python: FINEP, CNPq, CAPES, FAPESP, EMBRAPII, SENAI
- [x] Migrar scrapers TypeScript (GrantWatch, inteligencia-ai) — criar bridge
- [x] Integrar coletor IA-Brasil (DOU, CGEE, MCTI, CGU)
- [x] Integrar ETL InvestIA (Câmara, Senado, DOU)
- [x] Criar `src/scrapers/grants/` para editais
- [x] Criar `src/scrapers/artigos/` para artigos (arXiv, SemanticScholar)
- [x] Criar `src/scrapers/gov/` para dados governamentais
- [x] Retry com backoff, rate limiting, proxy rotation
- [x] Testes unitários para cada scraper

### Fase 4 — Classificação ML ✅
- [x] Classificador de relevância (SetFit + MiniLM)
- [x] Embeddings unificados (ChromaDB)
- [x] Confidence gate (conservador/moderado/agressivo)
- [x] Retreinamento incremental (a cada 20 feedbacks)
- [x] Integrar classificador .NET (buscador_de_grants) via bridge
- [x] Métricas: precision, recall, F1

### Fase 5 — Bot Telegram Unificado ✅
- [x] Bot único (migrar do CognitiaBrain)
- [x] Comandos: /start, /status, /pause, /resume, /help, /metrics
- [x] Botões inline para feedback (👍/👎)
- [x] Notificações formatadas com confiança
- [x] Conversation memory para diálogos contextuais
- [x] Integrar com classifier e deduplicação

### Fase 6 — Dashboard Web ✅
- [x] FastAPI + Jinja2 + HTMX
- [x] Visualização de grants + artigos
- [x] Filtros por fonte, data, relevância
- [x] Métricas de performance
- [x] Gestão de foco de pesquisa

### Fase 7 — Inteligência Ativa ✅
- [x] FocusManager (inferência de foco)
- [x] Detecção de conexões (cosseno + grafo)
- [x] Síntese de escrita por tema
- [x] Scout web automatizado
- [x] Weekly digest

### Fase 8 — Integração e Polish ✅
- [x] Testes unitários e e2e
- [x] Documentação completa
- [x] CI/CD (GitHub Actions)
- [x] Deploy automatizado
- [x] Migração de dados históricos

---

## Arquitetura Final

```
cognitia-brain-unified/
├── src/
│   ├── scrapers/          # TODOS os scrapers unificados (Python)
│   │   ├── grants/        # FINEP, CNPq, CAPES, FAPESP, etc.
│   │   ├── artigos/       # arXiv, SemanticScholar, feeds
│   │   └── gov/           # DOU, CGEE, MCTI, CGU, Câmara, Senado
│   ├── ml/                # Classificador, embeddings, ChromaDB
│   ├── bot/               # Telegram bot unificado
│   ├── web/               # Dashboard (FastAPI ou Next.js)
│   ├── shared/            # Config, database, logger, eventos
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
| **Linguagem** | Python 3.11+ | NLP/ML nativo, ChromaDB, unificação |
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

| Métrica | Meta | Status |
|---------|------|--------|
| Cobertura de fontes | 15+ scrapers funcionando | ✅ |
| Deduplicação | 0% de notificações duplicadas | ✅ |
| Precisão (relevância) | > 85% de notificações úteis | ✅ |
| Latência (scrape → notify) | < 5 minutos | ✅ |
| Feedback loop | Retreinamento a cada 20 labels | ✅ |
| Código morto | 0% (tudo documentado e testado) | ✅ |

---

## Riscos e Mitigações

| Risco | Mitigação |
|-------|-----------|
| Mudança de layout nas fontes | Múltiplos seletores + fallback |
| Drift do modelo | Retreinamento periódico |
| Rate limit Telegram | Batching + retry com backoff |
| Dados de feedback enviesados | Diversity sampling |
| Conflito de porta web | Porta canônica 8081 |
| Complexidade da integração | Fases incrementais, testes a cada fase |

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
