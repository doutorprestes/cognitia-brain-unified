# Issue #1 — Estrutura do Projeto e Ambiente

**Labels:** `infraestrutura`, `fase-1`
**Estimate:** 30 min

## Descrição

Criar estrutura de diretórios, ambiente virtual e dependências do projeto CognitiaBrain Unified.

## Tarefas

- [ ] Criar `/home/jalp/Projetos/cognitia-brain-unified/` com subdirs: `src/cognitia/`, `src/grants/`, `src/shared/`, `src/web/`, `src/scripts/`, `tests/`, `docs/`
- [ ] Criar `requirements.txt` com dependências fixadas
- [ ] Criar `.env.example` (TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID, DB_PATH, OPENROUTER_API_KEY, OLLAMA_CLOUD_API_KEY)
- [ ] Criar `config.py` (carrega .env, constantes do projeto)
- [ ] Criar `README.md` com instruções de setup
- [ ] Criar `tests/__init__.py`

## Dependências

```
python-telegram-bot==21.0.1
sentence-transformers==2.2.2
scikit-learn==1.3.0
joblib==1.3.2
apscheduler==3.10.4
beautifulsoup4==4.12.2
playwright==1.40.0
python-dotenv==1.0.0
chromadb==0.4.0
fastapi==0.104.0
uvicorn==0.24.0
jinja2==3.1.2
httpx==0.25.0
```

## Critérios de Aceite

- [ ] `pip install -r requirements.txt` funciona sem erros
- [ ] `python -c "import config"` carrega sem erros
- [ ] Estrutura de diretórios criada conforme especificação

## Output Esperado

```
cognitia-brain-unified/
├── src/
│   ├── cognitia/
│   ├── grants/
│   ├── shared/
│   ├── web/
│   └── scripts/
├── tests/
├── docs/
├── requirements.txt
├── .env.example
└── README.md
```
