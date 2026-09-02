# CognitiaBrain Unified — Roadmap

> Sistema unificado de monitoramento acadêmico: grants + artigos + IA.

## Status: 🔄 EM DESENVOLVIMENTO

**Última atualização:** 2026-09-02

---

## Estado Atual

### ✅ Funcional
- Backend FastAPI com endpoints /api/stats, /api/items, /api/search, /api/feedback, /api/health
- Scraper arXiv (20 artigos relevantes)
- Scraper OpenAlex (30 artigos relevantes)
- Banco SQLite com 49 artigos (deduplicação por hash)
- Filtro de relevância por palavras-chave (config/interesses.yaml)
- Telegram Mini App com UI responsiva (dark mode)
- Grill de navegação (5 botões: Início, Buscar, Editais, Perfil, Config)
- Cards com badges por categoria (Robótica, LLM, Multi-Agent, Alignment)
- Feedback (👍/👎) com persistência no banco
- Pull-to-refresh
- Paginação infinita (scroll carrega mais)
- Busca por título/snippet/source
- Deploy via Cloudflare Tunnel (público, HTTPS)
- Git sincronizado com GitHub

### ❌ Não Funcional / Incompleto
- Scrapers CAPES, CNPq, FINEP, DOU (retornam lixo ou erro)
- Sem sistema de editais reais (placeholder)
- Sem sistema de perfil (placeholder)
- Sem sistema de configurações (placeholder)
- Sem Telegram bot (notificações)

---

## Issues Atômicas (para modelo menor)

### Sprint 1 — Fundação do Mini App ✅
- [x] #001 Adicionar pull-to-refresh na lista de artigos
- [x] #002 Implementar paginação infinita (scroll carrega mais)
- [x] #003 Adicionar indicador novos desde última visita
- [x] #004 Criar tela vazia quando não há itens
- [x] #005 Melhorar skeleton loading
- [x] #006 Criar endpoint GET /api/search
- [x] #007 Implementar busca no banco (LIKE em title, snippet, source)
- [x] #008 Criar UI de busca (campo input, filtros, resultados)
- [x] #009 Salvar histórico de buscas no Telegram CloudStorage
- [x] #010 Adicionar busca por categoria (robot, llm, agent, alignment)

### Sprint 2 — Editais (Grants)
- [ ] #011 Refinar scraper FAPESP (parser específico de editais)
- [ ] #012 Refinar scraper CNPq (parser específico de chamadas)
- [ ] #013 Refinar scraper CAPES (parser específico de bolsas)
- [ ] #014 Refinar scraper FINEP (parser específico de subvenção)
- [ ] #015 Refinar scraper DOU (seção 3, editais de fomento)
- [ ] #016 Criar tabela grants no banco (status, deadline, etc.)
- [ ] #017 Criar UI de editais (cards com status: aberto/encerrado)
- [ ] #018 Adicionar filtro por agência fomentadora
- [ ] #019 Implementar alertas de novos editais (notificação Telegram)

### Sprint 3 — Perfil ✅
- [ ] #020 Criar endpoint GET/PUT /api/profile
- [ ] #021 Criar UI de perfil (áreas de interesse, estatísticas)
- [ ] #022 Implementar seleção de áreas de interesse (checkboxes)
- [ ] #023 Salvar perfil no Telegram CloudStorage
- [ ] #024 Filtrar artigos no frontend baseado no perfil
- [ ] #025 Criar tela de estatísticas (feedbacks dados, artigos abertos)

### Sprint 4 — Configurações ✅
- [ ] #026 Criar endpoint GET/PUT /api/config
- [ ] #027 Criar UI de configurações (tema, idioma, notificações)
- [ ] #028 Implementar modo claro/escuro (seguir Telegram ou manual)
- [ ] #029 Implementar frequência de coleta (1h, 6h, 24h)
- [ ] #030 Adicionar botão limpar cache

### Sprint 5 — Telegram Bot ✅
- [ ] #031 Criar bot Telegram (python-telegram-bot v21)
- [ ] #032 Implementar comandos: /start, /status, /pause, /resume, /help
- [ ] #033 Implementar notificações de novos artigos
- [ ] #034 Implementar notificações de novos editais
- [ ] #035 Adicionar botões inline para feedback (👍/👎)
- [ ] #036 Integrar bot com Mini App (WebApp button)

### Sprint 6 — Qualidade e Polish ✅
- [ ] #037 Adicionar testes unitários para scrapers
- [ ] #038 Adicionar testes unitários para API
- [ ] #039 Adicionar testes e2e para Mini App
- [ ] #040 Configurar CI/CD (GitHub Actions)
- [ ] #041 Documentar API (OpenAPI/Swagger)
- [ ] #042 Criar documentação de contribuição

---

## Planejamento de Execução

### Semana 1 (2026-09-03) ✅
| Dia | Tarefa | Issue |
|-----|--------|-------|
| 1 | Pull-to-refresh + paginação + busca | #001-#10 |

### Semana 2 (2026-09-04 a 2026-09-10)
**Foco:** Editais reais

| Dia | Tarefa | Issue |
|-----|--------|-------|
| 1 | Refinar scraper FAPESP | #11 |
| 2 | Refinar scraper CNPq | #12 |
| 3 | Refinar scraper CAPES | #13 |
| 4 | Refinar scraper FINEP | #14 |
| 5 | Refinar scraper DOU | #15 |
| 6 | Tabela grants + UI | #16, #17 |
| 7 | Filtros + alertas | #18, #19 |

### Semana 3 (2026-09-11 a 2026-09-17)
**Foco:** Perfil + Config + Bot

| Dia | Tarefa | Issue |
|-----|--------|-------|
| 1 | Endpoint + UI de perfil | #20, #21 |
| 2 | Áreas de interesse | #22, #23, #24 |
| 3 | Estatísticas | #25 |
| 4 | Endpoint + UI de config | #26, #27 |
| 5 | Tema + frequência | #28, #29, #30 |
| 6 | Bot Telegram básico | #31, #32 |
| 7 | Notificações + integração | #33, #34, #35, #36 |

### Semana 4 (2026-09-18 a 2026-09-24)
**Foco:** Qualidade e lançamento

| Dia | Tarefa | Issue |
|-----|--------|-------|
| 1 | Testes unitários scrapers | #37 |
| 2 | Testes unitários API | #38 |
| 3 | Testes e2e Mini App | #39 |
| 4 | CI/CD | #40 |
| 5 | Documentação | #41, #42 |
| 6 | Beta testing + ajustes | — |
| 7 | Lançamento v1.0 | — |

---

## Stack Técnica

| Componente | Ferramenta | Status |
|------------|------------|--------|
| Linguagem | Python 3.12 | ✅ |
| Backend | FastAPI + Uvicorn | ✅ |
| Frontend | HTML/JS vanilla (Telegram Mini App) | ✅ |
| Banco | SQLite (WAL mode) | ✅ |
| Scrapers | httpx + BeautifulSoup + Playwright | ⚠️ Parcial |
| Deploy | Cloudflare Tunnel | ✅ |
| Bot | python-telegram-bot v21 | ❌ |
| Testes | pytest | ❌ |
| CI/CD | GitHub Actions | ❌ |

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
