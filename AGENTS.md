# CognitiaBrain Unified — Development Guide

> Sistema unificado de monitoramento acadêmico: grants + artigos + IA.

## Project Overview

CognitiaBrain Unified é um pipeline Python que coleta, classifica e notifica sobre **editais de fomento** e **artigos científicos**, aprendendo com feedback do usuário para melhorar relevância ao longo do tempo.

**Stack:** Python 3.11+, SQLite, ChromaDB, FastAPI, python-telegram-bot, sentence-transformers, scikit-learn, Playwright.

## Commands

```bash
# Setup (uma vez)
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/python -m playwright install chromium
cp .env.example .env  # configure suas chaves

# CLI
.venv/bin/python cli.py run                     # executa pipeline uma vez
.venv/bin/python cli.py bot                    # inicia bot Telegram
.venv/bin/python cli.py scrape                 # só coleta
.venv/bin/python cli.py classify               # só classifica
.venv/bin/python cli.py status                 # estatísticas

# Web dashboard
uvicorn src.web.main:app --port 8081          # dashboard em http://localhost:8081

# Testes
pytest tests/ -v                               # todos os testes
pytest tests/unit/ -v                          # unitários
pytest tests/e2e/ -v                           # end-to-end

# Diagnóstico
.venv/bin/python cli.py diagnose              # verifica ambiente
```

## Architecture

- **Entrypoints**: `src/cognitia/bot.py` (Telegram), `src/web/main.py` (FastAPI), `cli.py` (CLI)
- **LLM**: `LLMClient.generate()` tenta OpenRouter e cai para Ollama Cloud
- **Vector DB**: ChromaDB persistente em `.chromadb/`, collection `cognitia_vectors`
- **Classificador**: SetFit + MiniLM (`src/shared/classifier.py`)
- **Scrapers**: Playwright + BeautifulSoup (`src/grants/`)
- **Storage**: SQLite em `data/cognitia.db`

## Code Style

- Use descriptive variable names
- Follow existing patterns in the codebase
- Extract complex conditions into meaningful boolean variables
- All code, docs and commits in **Brazilian Portuguese (pt-BR)**

## Gotchas

- **Porta canônica da web = 8081** (Caddyfile proxy `:8443` → `127.0.0.1:8081`)
- **Hash de deduplicação**: SHA-256 de `title + url` (normalizado: lowercase, strip)
- **Confidence gate**: conservador (0.8), moderado (0.6), agressivo (0.5)
- **Retreinamento**: incremental a cada 20 novos feedbacks
- **Rate limit Telegram**: batching + retry com backoff (máx 3 tentativas)
- **Scrapers JS-rendered**: Playwright com wait_ms=5000 por padrão

## Data Sources

### Grants (Editais)
- FINEP, CNPq, CAPES, FAPESP, EMBRAPII, SENAI CIMATEC, Unicamp/Inova

### Artigos
- PDFs locais, URLs, feeds RSS, arXiv

## Testing

- Unit tests: `tests/unit/`
- E2E tests: `tests/e2e/`
- Fixtures: `tests/fixtures/`
- Run: `pytest tests/ -v --pool=forks --maxWorkers=1`

## CI/CD

- GitHub Actions: `.github/workflows/daily.yml`
- Roda a cada 6h (cron)
- Testes → Build → Deploy

## References

- [CognitiaBrain](https://github.com/doutorprestes/cognitia-brain) — monitor de artigos (original)
- [GrantWatch](https://github.com/doutorprestes/grantwatch) — monitor de editais (original)
- [Scrapy](https://scrapy.org/) — framework de scraping
- [ChromaDB](https://trychroma.com/) — vector database
- [SetFit](https://github.com/huggingface/setfit) — few-shot classification
