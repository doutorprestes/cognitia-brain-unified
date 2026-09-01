# Arquitetura Atual — CognitiaBrain Unified

> Inventário dos 7 projetos importados (615 arquivos, ~314k linhas)

## Projetos Importados

### 1. CognitiaBrain ()
- **Função:** Monitor de artigos científicos com IA
- **Arquivos:** 25+ módulos Python
- **Componentes:** bot.py, pipeline.py, llm_client.py, graph.py, proativo.py, scheduler.py, scout.py
- **Stack:** python-telegram-bot, ChromaDB, OpenRouter/Ollama, FastAPI

### 2. GrantWatch ()
- **Função:** Monitor de editais de fomento
- **Arquivos:** 10 scrapers TypeScript
- **Componentes:** finep.ts, cnpq.ts, capes.ts, fapesp.ts, embrapii.ts, senaicimatec.ts, unicamp.ts, inova.ts
- **Stack:** Playwright, BeautifulSoup

### 3. IA-Brasil (, , , )
- **Função:** Coletor de dados públicos brasileiros
- **Arquivos:** 40+ módulos Python
- **Componentes:** collector (DOU, CGEE, MCTI, CGU), 20+ módulos (admin, analytics, audit, auth, collector, data_quality, engagement, evidence_ingestion, export, feed, linking, llm_assist, pbia, pbia_parser, pipeline_health, public_portal, scoring, timeline, webhook)
- **Stack:** FastAPI, SQLAlchemy, Alembic

### 4. InvestIA (, , )
- **Função:** ETL de dados de investimento
- **Arquivos:** 15+ módulos Python
- **Componentes:** etl (camara_api, cnpq_api, dou_api, finep_api, mcti_api, senado_api, compras_gov_api, mgi_gov360_api), api, backend
- **Stack:** FastAPI, httpx

### 5. buscador_de_grants ()
- **Função:** Buscador de grants com ML.NET
- **Arquivos:** C# (.cs), CSV data
- **Componentes:** FinepScraperService.cs, GrantClassifier (.mlnet), Grant.cs
- **Stack:** .NET, ML.NET

### 6. grantwatch_evolution ()
- **Função:** Dashboard Next.js
- **Arquivos:** brain, core, dashboard, data, pages, scripts
- **Stack:** Next.js, React

### 7. inteligencia-ai (, )
- **Função:** Scrapers + webapp
- **Arquivos:** scrapers (bolsas_exterior, cnpq, fapesp, finep, portal_inovacao), src (scrapers, utils)
- **Stack:** Node.js/TypeScript, Cheerio, Axios

## Sobreposições Identificadas

| Fonte | Projetos |
|-------|----------|
| FINEP | GrantWatch, inteligencia-ai, buscador_de_grants |
| CNPq | GrantWatch, inteligencia-ai, InvestIA |
| CAPES | GrantWatch, inteligencia-ai |
| FAPESP | GrantWatch, inteligencia-ai |
| DOU | IA-Brasil, InvestIA |
| Câmara | InvestIA, IA-Brasil |
| Senado | InvestIA |

## Diretórios Vazios (a serem preenchidos)

-  — config.py, database.py, logger.py (parciais)
-  — vazio
-  — vazio
-  — vazio
-  — vazio

## Próximos Passos

1. Consolidar scrapers em  (grants, artigos, gov)
2. Criar classificador ML em 
3. Criar bot unificado em 
4. Criar dashboard em 
5. Mover código legado para 
