# CognitiaBrain Unified — Roadmap

> Sistema unificado de monitoramento acadêmico: grants + artigos + IA.

## Status: 🔄 EM DESENVOLVIMENTO

**Última atualização:** 2026-09-02

---

## Estado Atual

### ✅ Funcional
- Backend FastAPI com endpoints `/api/stats`, `/api/items`, `/api/feedback`, `/api/health`
- Scraper arXiv (20 artigos relevantes, filtros por categoria)
- Scraper OpenAlex (30 artigos relevantes, sem rate limit)
- Banco SQLite com 49 artigos (deduplicação por hash)
- Filtro de relevância por palavras-chave (config/interesses.yaml)
- Telegram Mini App com UI responsiva (dark mode)
- Grill de navegação (5 botões: Início, Buscar, Editais, Perfil, Config)
- Cards com badges por categoria (Robótica, LLM, Multi-Agent, Alignment)
- Feedback (👍/👎) com persistência no banco
- Deploy via Cloudflare Tunnel (público, HTTPS)
- Git sincronizado com GitHub

### ❌ Não Funcional / Incompleto
- Scrapers CAPES, CNPq, FINEP, DOU (retornam lixo ou erro)
- Sem sistema de busca (placeholder)
- Sem sistema de editais reais (placeholder)
- Sem sistema de perfil (placeholder)
- Sem sistema de configurações (placeholder)
- Sem Telegram bot (notificações)
- Sem pull-to-refresh / paginação
- Sem pull request / code review

---

## Issues Atômicas (para modelo menor)

### Sprint 1 — Fundação do Mini App
- [ ] **#001** Adicionar pull-to-refresh na lista de artigos
- [ ] **#002** Implementar paginação infinita (scroll carrega mais)
- [ ] **#003** Adicionar indicador "novos desde última visita"
- [ ] **#004** Criar tela vazia quando não há itens
- [ ] **#005** Melhorar skeleton loading (mais cards, animação suave)

### Sprint 2 — Busca
- [ ] **#006** Criar endpoint `GET /api/search?q=&type=&period=`
- [ ] **#007** Implementar busca no banco (LIKE em title, snippet, source)
- [ ] **#008** Criar UI de busca (campo input, filtros, resultados)
- [ ] **#009** Salvar histórico de buscas no Telegram CloudStorage
- [ ] **#010** Adicionar busca por categoria (robot, llm, agent, alignment)

### Sprint 3 — Editais (Grants)
- [ ] **#011** Refinar scraper FAPESP (parser específico de editais)
- [ ] **#012** Refinar scraper CNPq (parser específico de chamadas)
- [ ] **#013** Refinar scraper CAPES (parser específico de bolsas)
- [ ] **#014** Refinar scraper FINEP (parser específico de subvenção)
- [ ] **#015** Refinar scraper DOU (seção 3, editais de fomento)
- [ ] **#016** Criar tabela `grants` no banco (status, deadline, etc.)
- [ ] **#017** Criar UI de editais (cards com status: aberto/encerrado)
- [ ] **#018** Adicionar filtro por agência fomentadora
- [ ] **#019** Implementar alertas de novos editais (notificação Telegram)

### Sprint 4 — Perfil
- [ ] **#020** Criar endpoint `GET/PUT /api/profile`
- [ ] **#021** Criar UI de perfil (áreas de interesse, estatísticas)
- [ ] **#022** Implementar seleção de áreas de interesse (checkboxes)
- [ ] **#023** Salvar perfil no Telegram CloudStorage
- [ ] **#024** Filtrar artigos no frontend baseado no perfil
- [ ] **#025** Criar tela de estatísticas (feedbacks dados, artigos abertos)

### Sprint 5 — Configurações
- [ ] **#026** Criar endpoint `GET/PUT /api/config`
- [ ] **#027** Criar UI de configurações (tema, idioma, notificações)
- [ ] **#028** Implementar modo claro/escuro (seguir Telegram ou manual)
- [ ] **#029** Implementar frequência de coleta (1h, 6h, 24h)
- [ ] **#030** Adicionar botão "limpar cache"

### Sprint 6 — Telegram Bot
- [ ] **#031** Criar bot Telegram (python-telegram-bot v21)
- [ ] **#032** Implementar comandos: /start, /status, /pause, /resume, /help
- [ ] **#033** Implementar notificações de novos artigos
- [ ] **#034** Implementar notificações de novos editais
- [ ] **#035** Adicionar botões inline para feedback (👍/👎)
- [ ] **#036** Integrar bot com Mini App (WebApp button)

### Sprint 7 — Qualidade e Polish
- [ ] **#037** Adicionar testes unitários para scrapers
- [ ] **#038** Adicionar testes unitários para API
- [ ] **#039** Adicionar testes e2e para Mini App
- [ ] **#040** Configurar CI/CD (GitHub Actions)
- [ ] **#041** Documentar API (OpenAPI/Swagger)
- [ ] **#042** Criar documentação de contribuição

---

## Planejamento de Execução

### Semana 1 (2026-09-03 a 2026-09-09)
**Foco:** Mini App funcional e busca

| Dia | Tarefa | Issue |
|-----|--------|-------|
| 1 | Pull-to-refresh + paginação | #001, #002 |
| 2 | Indicador de novos + tela vazia | #003, #004 |
| 3 | Skeleton melhorado | #005 |
| 4 | Endpoint de busca | #006, #007 |
| 5 | UI de busca | #008, #009 |
| 6 | Busca por categoria | #010 |
| 7 | Testes e ajustes | — |

### Semana 2 (2026-09-10 a 2026-09-16)
**Foco:** Editais reais

| Dia | Tarefa | Issue |
|-----|--------|-------|
| 1 | Refinar scraper FAPESP | #011 |
| 2 | Refinar scraper CNPq | #012 |
| 3 | Refinar scraper CAPES | #013 |
| 4 | Refinar scraper FINEP | #14 |
| 5 | Refinar scraper DOU | #015 |
| 6 | Tabela grants + UI | #016, #017 |
| 7 | Filtros + alertas | #018, #019 |

### Semana 3 (2026-09-17 a 2026-09-23)
**Foco:** Perfil + Config + Bot

| Dia | Tarefa | Issue |
|-----|--------|-------|
| 1 | Endpoint + UI de perfil | #020, #021 |
| 2 | Áreas de interesse | #022, #023, #024 |
| 3 | Estatísticas | #025 |
| 4 | Endpoint + UI de config | #026, #027 |
| 5 | Tema + frequência | #028, #029, #030 |
| 6 | Bot Telegram básico | #031, #032 |
| 7 | Notificações + integração | #033, #034, #035, #036 |

### Semana 4 (2026-09-24 a 2026-09-30)
**Foco:** Qualidade e lançamento

| Dia | Tarefa | Issue |
|-----|--------|-------|
| 1 | Testes unitários scrapers | #037 |
| 2 | Testes unitários API | #038 |
| 3 | Testes e2e Mini App | #039 |
| 4 | CI/CD | #040 |
| 5 | Documentação | #041, #042 |
| 6 | Beta testing + ajustes | — |
| 7 | Lançamento v1.0 | — |

---

## Arquitetura

```
cognitia-brain-unified/
├── src/
│   ├── scrapers/
│   │   ├── artigos/       # arXiv, OpenAlex (✅ funcional)
│   │   ├── grants/        # FAPESP, CNPq, CAPES, FINEP (❌ quebrado)
│   │   └── gov/           # DOU (❌ quebrado)
│   ├── web/
│   │   └── pwa.py         # FastAPI endpoints (✅ funcional)
│   ├── bot/
│   │   └── bot.py         # Telegram bot (❌ não iniciado)
│   └── shared/
│       ├── database.py    # SQLite (✅ funcional)
│       ├── relevancia.py  # Filtro de relevância (✅ funcional)
│       └── config.py      # Config centralizado (✅ funcional)
├── static/
│   └── miniapp/
│       └── index.html     # Telegram Mini App (✅ funcional)
├── config/
│   └── interesses.yaml    # Perfil de interesses (✅ funcional)
├── data/
│   └── cognitia.db        # Banco SQLite (✅ 49 artigos)
├── tests/                 # (❌ vazio)
├── issues/                # (❌ vazio)
└── docs/                  # (❌ vazio)
```

---

## Stack Técnica

| Componente | Ferramenta | Status |
|------------|------------|--------|
| **Linguagem** | Python 3.12 | ✅ |
| **Backend** | FastAPI + Uvicorn | ✅ |
| **Frontend** | HTML/JS vanilla (Telegram Mini App) | ✅ |
| **Banco** | SQLite (WAL mode) | ✅ |
| **Scrapers** | httpx + BeautifulSoup + Playwright | ⚠️ Parcial |
| **Deploy** | Cloudflare Tunnel | ✅ |
| **Bot** | python-telegram-bot v21 | ❌ |
| **Testes** | pytest | ❌ |
| **CI/CD** | GitHub Actions | ❌ |

---

## Métricas de Sucesso

| Métrica | Meta | Atual |
|---------|------|-------|
| Artigos relevantes | 100+ | 49 |
| Editais funcionando | 5 fontes | 0 |
| Scrapers funcionando | 10 | 2 |
| Cobertura de testes | > 80% | 0% |
| Tempo de resposta API | < 200ms | ~100ms |
| Uptime | > 99% | ~95% |

---

## Referências

- [Telegram Mini Apps](https://core.telegram.org/bots/webapps)
- [FastAPI](https://fastapi.tiangolo.com/)
- [OpenAlex API](https://docs.openalex.org/)
- [arXiv API](https://arxiv.org/help/api)
- [python-telegram-bot](https://python-telegram-bot.org/)
