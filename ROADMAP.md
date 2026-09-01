# CognitiaBrain Unified — Roadmap

> Sistema unificado de monitoramento acadêmico: grants + artigos + IA.

## Situação Atual

**7 projetos importados** (código legado, sem modificações):
- CognitiaBrain (artigos + LLM + Telegram bot)
- GrantWatch (editais + scrapers TS)
- IA-Brasil (coletor dados públicos + 20+ módulos)
- InvestIA (ETL + API + backend)
- buscador_de_grants (.NET + ML.NET)
- grantwatch_evolution (Next.js dashboard)
- inteligencia-ai (scrapers + webapp)

**Total:** ~220 arquivos, ~314k linhas de código, 12 subdiretórios em `src/`.

**Problema:** Código fragmentado, sem padronização, com sobreposição de funcionalidades e sem integração.

---

## Fases

### Fase 1 — Inventário e Limpeza (Semana 1)
- [ ] Mapear todas as fontes de dados e scrapers
- [ ] Identificar sobreposções e duplicações
- [ ] Remover código morto e dependências não utilizadas
- [ ] Padronizar estrutura de diretórios
- [ ] Documentar arquitetura atual (como-está)

### Fase 2 — Fundação Unificada (Semana 1-2)
- [ ] Módulo de configuração centralizado (`.env` + YAML)
- [ ] Banco de dados SQLite unificado (schema padronizado)
- [ ] Sistema de deduplicação (hash SHA-256)
- [ ] Logger e tratamento de erros centralizados
- [ ] Pipeline de eventos assíncrono

### Fase 3 — Scrapers Unificados (Semana 2-3)
- [ ] Classe base abstrata `BaseScraper` (interface única)
- [ ] Migrar scrapers Python: FINEP, CNPq, CAPES, FAPESP, EMBRAPII, SENAI
- [ ] Migrar scrapers TypeScript para Python (ou criar bridge)
- [ ] Integrar coletor IA-Brasil ( Dou, CGEE, MCTI, CGU )
- [ ] Integrar ETL InvestIA ( Câmara, Senado, DOU )
- [ ] Retry com backoff, rate limiting, proxy rotation
- [ ] Testes unitários para cada scraper

### Fase 4 — Classificação ML (Semana 3-4)
- [ ] Classificador de relevância (SetFit + MiniLM)
- [ ] Embeddings unificados (ChromaDB)
- [ ] Confidence gate (conservador/moderado/agressivo)
- [ ] Retreinamento incremental (a cada 20 feedbacks)
- [ ] Integrar classificador .NET (buscador_de_grants) via bridge
- [ ] Métricas: precision, recall, F1

### Fase 5 — Bot Telegram Unificado (Semana 4-5)
- [ ] Bot único (migrar do CognitiaBrain)
- [ ] Comandos: /start, /status, /pause, /resume, /help
- [ ] Botões inline para feedback (👍/👎)
- [ ] Notificações formatadas com confiança
- [ ] Conversation memory para diálogos contextuais
- [ ] Integrar com classifier e deduplicação

### Fase 6 — Dashboard Web (Semana 5-6)
- [ ] FastAPI + Jinja2 + HTMX (ou migrar Next.js)
- [ ] Visualização de grants + artigos
- [ ] Filtros por fonte, data, relevância
- [ ] Métricas de performance
- [ ] Gestão de foco de pesquisa

### Fase 7 — Inteligência Ativa (Semana 6-7)
- [ ] FocusManager (inferência de foco)
- [ ] Detecção de conexões (cosseno + grafo)
- [ ] Síntese de escrita por tema
- [ ] Scout web automatizado
- [ ] Weekly digest

### Fase 8 — Integração e Polish (Semana 7-8)
- [ ] Testes unitários e e2e
- [ ] Documentação completa
- [ ] CI/CD (GitHub Actions)
- [ ] Deploy automatizado
- [ ] Migração de dados históricos

---

## Arquitetura Alvo

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
├── data/                  # SQLite + ChromaDB
└── models/                # Modelos treinados (.pkl)
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

| Métrica | Meta |
|---------|------|
| Cobertura de fontes | 15+ scrapers funcionando |
| Deduplicação | 0% de notificações duplicadas |
| Precisão (relevância) | > 85% de notificações úteis |
| Latência (scrape → notify) | < 5 minutos |
| Feedback loop | Retreinamento a cada 20 labels |
| Código morto | 0% (tudo documentado e testado) |

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
